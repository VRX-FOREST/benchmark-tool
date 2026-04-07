"""
tasks.py — Tâches Celery : Deep Research Benchmark.

Philosophie : qualité > vitesse.
Le système fait plusieurs passes de collecte pour chaque produit,
croise les sources, et ne s'arrête que quand il a épuisé ses options.
"""
import uuid
import asyncio
from celery_app import celery
from database import (
    update_benchmark_status, update_benchmark_criteria,
    save_product,
)
from agent import (
    research_market_landscape,
    select_products,
    define_criteria,
    structure_scraped_data,
    deep_extract_missing_fields,
    enrich_product_from_knowledge,
)
from scraper import scrape_product, search_web


def _run_async(coro):
    """Helper pour exécuter du code async dans Celery."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _count_completeness(data: dict, total_fields: int) -> float:
    """Calcule le taux de remplissage des données."""
    if total_fields == 0:
        return 0.0
    filled = sum(1 for v in data.values() if v is not None)
    return filled / total_fields


def _deep_scrape_product(
    product_name: str,
    brand: str,
    search_queries: list[str],
    known_urls: list[str],
    criteria: list[dict],
    total_fields: int,
) -> dict:
    """
    Collecte approfondie pour UN produit.
    
    Stratégie multi-passes :
    1. D'abord, scrape les URLs connues (si fournies)
    2. Puis, lance chaque requête de recherche et scrape les meilleurs résultats
    3. Extraction des données après chaque lot de sources
    4. Si complétude < 70%, génère de nouvelles requêtes ciblées sur les champs manquants
    5. En dernier recours, enrichissement IA
    """
    all_sources = []       # [{"url": ..., "text": ..., "source_type": ...}]
    urls_scraped = set()
    extracted_data = {}
    sources_per_field = {}
    image_url = ""
    best_source_url = ""

    # Sites prioritaires en France
    priority_domains = [
        "amazon.fr", "fnac.com", "decathlon.fr", "boulanger.com",
        "cdiscount.com", "darty.com", "lesnumeriques.com",
        "rtings.com", "materiel.net", "son-video.com",
        "idealo.fr", "quechoisir.org",
    ]

    def _is_priority(url: str) -> bool:
        return any(d in url for d in priority_domains)

    def _scrape_url(url: str, source_type: str = "web") -> dict | None:
        """Scrape une URL et retourne les données si succès."""
        if url in urls_scraped or not url:
            return None
        urls_scraped.add(url)

        page = _run_async(scrape_product(url))
        if not page.get("success") or len(page.get("text", "")) < 100:
            return None

        return {
            "url": url,
            "text": page["text"],
            "image_url": page.get("image_url", ""),
            "source_type": source_type,
        }

    def _search_and_scrape(query: str, max_results: int = 5) -> list[dict]:
        """Recherche + scrape des résultats."""
        results = _run_async(search_web(query, num_results=max_results))
        scraped = []

        # Trier : sources prioritaires d'abord
        sorted_results = sorted(
            results, 
            key=lambda r: (0 if _is_priority(r.get("url", "")) else 1)
        )

        for r in sorted_results:
            url = r.get("url", "")
            data = _scrape_url(url, "search")
            if data:
                scraped.append(data)
        return scraped

    print(f"  [DEEP] Début collecte approfondie pour {product_name}")

    # ─── PASSE 1 : URLs connues ───
    if known_urls:
        for url in known_urls:
            data = _scrape_url(url, "known")
            if data:
                all_sources.append(data)
                if not image_url and data["image_url"]:
                    image_url = data["image_url"]
                if not best_source_url or _is_priority(url):
                    best_source_url = url

    print(f"  [DEEP] Passe 1 (URLs connues) : {len(all_sources)} sources")

    # ─── PASSE 2 : Requêtes de recherche fournies par l'IA ───
    for query in search_queries:
        if not query:
            continue
        new_sources = _search_and_scrape(query, max_results=5)
        for s in new_sources:
            all_sources.append(s)
            if not image_url and s["image_url"]:
                image_url = s["image_url"]
            if not best_source_url or _is_priority(s["url"]):
                best_source_url = s["url"]

    print(f"  [DEEP] Passe 2 (requêtes IA) : {len(all_sources)} sources cumulées")

    # ─── PREMIÈRE EXTRACTION ───
    if all_sources:
        combined_text = ""
        source_urls = []
        for s in all_sources:
            combined_text += f"\n\n--- Source: {s['url']} ---\n{s['text']}"
            source_urls.append(s["url"])

        try:
            result = structure_scraped_data(
                product_name, combined_text, criteria, source_urls
            )
            extracted_data = result.get("extracted", {})
            sources_per_field = result.get("sources_per_field", {})
            completeness = _count_completeness(extracted_data, total_fields)
            print(f"  [DEEP] Extraction 1 : complétude {completeness:.0%}")
        except Exception as e:
            print(f"  [DEEP] Erreur extraction 1 : {e}")
            completeness = 0.0
    else:
        completeness = 0.0

    # ─── PASSE 3 : Requêtes ciblées sur les champs manquants ───
    if completeness < 0.70:
        # Identifier les catégories avec le plus de champs manquants
        missing_categories = set()
        for cat in criteria:
            for field in cat.get("fields", []):
                unit_str = f" ({field['unit']})" if field.get("unit") else ""
                key = f"{cat['category']} > {field['name']}{unit_str}"
                if extracted_data.get(key) is None:
                    missing_categories.add(cat["category"])

        # Générer des requêtes ciblées
        targeted_queries = []
        if "Caractéristiques techniques" in missing_categories:
            targeted_queries.append(f"{product_name} specifications techniques poids dimensions")
            targeted_queries.append(f"{product_name} datasheet specs")
        if "Fonctionnalités" in missing_categories:
            targeted_queries.append(f"{product_name} fonctionnalités caractéristiques complètes")
        if "Expérience utilisateur" in missing_categories:
            targeted_queries.append(f"test {product_name} avis détaillé confort utilisation")
            targeted_queries.append(f"{product_name} review test complet")
        if "Données marché" in missing_categories:
            targeted_queries.append(f"{product_name} avis note moyenne comparatif")

        for query in targeted_queries:
            new_sources = _search_and_scrape(query, max_results=3)
            if new_sources:
                new_combined = ""
                new_urls = []
                for s in new_sources:
                    new_combined += f"\n\n--- Source: {s['url']} ---\n{s['text']}"
                    new_urls.append(s["url"])
                    all_sources.append(s)
                    if not image_url and s["image_url"]:
                        image_url = s["image_url"]

                # Extraction complémentaire sur les champs manquants
                try:
                    extracted_data, new_field_sources = deep_extract_missing_fields(
                        product_name, criteria, extracted_data, new_combined, new_urls
                    )
                    sources_per_field.update(new_field_sources)
                    completeness = _count_completeness(extracted_data, total_fields)
                    print(f"  [DEEP] Passe 3 ciblée : complétude {completeness:.0%}")
                except Exception as e:
                    print(f"  [DEEP] Erreur extraction complémentaire : {e}")

            if completeness >= 0.70:
                break

    print(f"  [DEEP] Passe 3 (requêtes ciblées) : {len(all_sources)} sources, complétude {completeness:.0%}")

    # ─── PASSE 4 : Enrichissement IA (dernier recours) ───
    if completeness < 0.50:
        print(f"  [DEEP] Passe 4 : enrichissement IA (complétude insuffisante)")
        try:
            extracted_data = enrich_product_from_knowledge(
                product_name, criteria, extracted_data
            )
            completeness = _count_completeness(extracted_data, total_fields)
            print(f"  [DEEP] Après enrichissement IA : complétude {completeness:.0%}")
        except Exception as e:
            print(f"  [DEEP] Erreur enrichissement : {e}")

    # Construire le résumé des sources
    source_summary = []
    for s in all_sources:
        source_summary.append({
            "url": s["url"],
            "type": s["source_type"],
        })

    print(f"  [DEEP] Terminé : {len(all_sources)} sources, {len(urls_scraped)} URLs testées, "
          f"complétude finale {completeness:.0%}")

    return {
        "extracted_data": extracted_data,
        "sources_per_field": sources_per_field,
        "source_summary": source_summary,
        "completeness": completeness,
        "image_url": image_url,
        "best_source_url": best_source_url,
        "urls_scraped_count": len(urls_scraped),
    }


@celery.task(bind=True, name="run_benchmark")
def run_benchmark(self, benchmark_id: str, product_type: str, config: dict):
    """
    Tâche principale : Deep Research Benchmark.
    """
    try:
        # ─── Phase 1.5 : Analyse du marché ───
        update_benchmark_status(
            benchmark_id, "selecting",
            "Phase préliminaire : analyse du marché et identification des segments...", 5
        )
        print(f"[BENCHMARK] Démarrage : {product_type}")

        market_research = research_market_landscape(product_type, config)
        print(f"[BENCHMARK] Analyse marché terminée : "
              f"{len(market_research.get('segments', []))} segments, "
              f"{len(market_research.get('leading_brands', []))} marques identifiées")

        # ─── Phase 2 : Sélection des produits ───
        update_benchmark_status(
            benchmark_id, "selecting",
            "Phase 2 : Sélection des produits les plus pertinents (analyse approfondie)...", 10
        )

        products = select_products(product_type, config, market_research)
        total_products = len(products)

        if not products:
            update_benchmark_status(benchmark_id, "error", "Aucun produit trouvé.", 0)
            return

        product_names = [p["name"] for p in products]
        print(f"[BENCHMARK] {total_products} produits sélectionnés : {product_names}")

        update_benchmark_status(
            benchmark_id, "selecting",
            f"{total_products} produits sélectionnés. Définition des critères...", 15
        )

        # ─── Phase 3 : Critères de comparaison ───
        update_benchmark_status(
            benchmark_id, "criteria",
            "Phase 3 : Détermination des critères de comparaison professionnels...", 20
        )

        criteria = define_criteria(product_type, market_research)
        update_benchmark_criteria(benchmark_id, criteria)

        total_fields = sum(len(cat.get("fields", [])) for cat in criteria)
        print(f"[BENCHMARK] {total_fields} critères définis en "
              f"{len(criteria)} catégories")

        update_benchmark_status(
            benchmark_id, "criteria",
            f"{total_fields} critères définis. Début de la collecte approfondie...", 25
        )

        # ─── Phase 4+5 : Collecte approfondie ───
        for i, product_info in enumerate(products):
            product_name = product_info["name"]
            brand = product_info.get("brand", "")
            search_queries = product_info.get("search_queries", [f"{product_name} prix avis test"])
            known_urls = product_info.get("known_urls", [])

            progress = 25 + int((i / total_products) * 65)

            update_benchmark_status(
                benchmark_id, "collecting",
                f"Phase 4 : Collecte approfondie de {product_name} ({i+1}/{total_products}) — "
                f"recherche multi-sources en cours...",
                progress
            )

            print(f"\n[BENCHMARK] ═══ Produit {i+1}/{total_products} : {product_name} ═══")

            # Deep scrape
            result = _deep_scrape_product(
                product_name=product_name,
                brand=brand,
                search_queries=search_queries,
                known_urls=known_urls,
                criteria=criteria,
                total_fields=total_fields,
            )

            # Extraire le prix
            price_min = None
            price_max = None
            for key, val in result["extracted_data"].items():
                if "prix" in key.lower() and val is not None:
                    try:
                        price_str = str(val).replace("€", "").replace(",", ".").replace(" ", "").strip()
                        price_val = float(price_str)
                        if price_min is None or price_val < price_min:
                            price_min = price_val
                        if price_max is None or price_val > price_max:
                            price_max = price_val
                    except (ValueError, TypeError):
                        pass

            # Fallback prix estimé
            if price_min is None and product_info.get("estimated_price"):
                price_min = product_info["estimated_price"]
                price_max = product_info["estimated_price"]

            # Sauvegarder le produit avec ses sources
            product_data = {
                "id": str(uuid.uuid4()),
                "name": product_name,
                "brand": brand,
                "image_url": result["image_url"],
                "source_url": result["best_source_url"],
                "price_min": price_min,
                "price_max": price_max,
                "data": result["extracted_data"],
                "completeness": result["completeness"],
                # Stocker les sources dans les données pour traçabilité
                "sources": result["source_summary"],
                "sources_per_field": result["sources_per_field"],
            }
            save_product(benchmark_id, product_data)

        # ─── Phase 6 : Terminé ───
        update_benchmark_status(
            benchmark_id, "done",
            f"Benchmark terminé ! {total_products} produits collectés en profondeur.", 100
        )
        print(f"\n[BENCHMARK] ═══ TERMINÉ : {total_products} produits ═══")

    except Exception as e:
        print(f"[BENCHMARK] ERREUR FATALE : {e}")
        import traceback
        traceback.print_exc()
        update_benchmark_status(
            benchmark_id, "error",
            f"Erreur : {str(e)}", 0
        )
        raise
