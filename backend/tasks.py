"""
tasks.py — Tâches Celery exécutées en arrière-plan.
V2 améliorée :
  - Stratégie de scraping multi-requêtes (plusieurs angles de recherche)
  - Fallback d'enrichissement IA si le scraping est pauvre
  - Meilleure gestion des erreurs
"""
import uuid
import asyncio
from celery_app import celery
from database import (
    update_benchmark_status, update_benchmark_criteria,
    save_product, get_benchmark
)
from agent import (
    select_products, define_criteria, structure_scraped_data,
    enrich_product_from_knowledge
)
from scraper import scrape_product, search_web


def _run_async(coro):
    """Helper pour exécuter du code async dans Celery (qui est synchrone)."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _scrape_with_multiple_queries(product_name: str, brand: str, search_query: str) -> dict:
    """
    Scrape un produit en essayant plusieurs stratégies de recherche.
    Retourne le meilleur résultat combiné.
    """
    all_text = ""
    image_url = ""
    source_url = ""
    urls_tried = set()

    # Stratégie : plusieurs requêtes de recherche complémentaires
    queries = [
        # Requête optimisée fournie par l'IA
        search_query,
        # Requête directe nom du produit
        f"{product_name} avis test",
        # Requête Amazon spécifique
        f"site:amazon.fr {product_name}",
        # Requête fiche technique
        f"{product_name} caractéristiques fiche technique",
    ]

    for query in queries:
        if not query:
            continue

        search_results = _run_async(search_web(query, num_results=5))

        for result in search_results:
            url = result.get("url", "")
            if not url or url in urls_tried:
                continue
            urls_tried.add(url)

            # Prioriser certaines sources fiables
            is_priority = any(domain in url for domain in [
                "amazon.fr", "fnac.com", "decathlon.fr", "cdiscount.com",
                "lesnumeriques.com", "rtings.com", "boulanger.com",
                "darty.com", "materiel.net"
            ])

            page_data = _run_async(scrape_product(url))
            if page_data.get("success") and len(page_data.get("text", "")) > 200:
                all_text += f"\n\n--- Source: {url} ---\n{page_data['text']}"

                if not image_url and page_data.get("image_url"):
                    image_url = page_data["image_url"]
                if not source_url or is_priority:
                    source_url = url

                # Si on a assez de texte, on arrête (économie de requêtes ScraperAPI)
                if len(all_text) > 8000:
                    break

        # Si on a déjà du bon contenu, pas besoin de toutes les requêtes
        if len(all_text) > 5000:
            break

    return {
        "text": all_text,
        "image_url": image_url,
        "source_url": source_url,
        "urls_tried": len(urls_tried),
    }


@celery.task(bind=True, name="run_benchmark")
def run_benchmark(self, benchmark_id: str, product_type: str, config: dict):
    """
    Tâche principale : exécute les 6 phases du benchmark.
    """
    try:
        # ─── Phase 2 : Sélection des produits ───
        update_benchmark_status(
            benchmark_id, "selecting",
            "Phase 2 : Sélection des produits les plus pertinents...", 10
        )

        products = select_products(product_type, config)
        total_products = len(products)

        if not products:
            update_benchmark_status(benchmark_id, "error", "Aucun produit trouvé.", 0)
            return

        # Afficher les produits sélectionnés dans le log
        product_names = [p["name"] for p in products]
        print(f"[BENCHMARK] Produits sélectionnés : {product_names}")

        update_benchmark_status(
            benchmark_id, "selecting",
            f"{total_products} produits sélectionnés. Définition des critères...", 20
        )

        # ─── Phase 3 : Modélisation des critères ───
        update_benchmark_status(
            benchmark_id, "criteria",
            "Phase 3 : Détermination des critères de comparaison...", 25
        )

        criteria = define_criteria(product_type)
        update_benchmark_criteria(benchmark_id, criteria)

        total_fields = sum(len(cat.get("fields", [])) for cat in criteria)
        print(f"[BENCHMARK] {total_fields} critères définis")

        update_benchmark_status(
            benchmark_id, "criteria",
            f"{total_fields} critères définis. Collecte en cours pour {total_products} produits...", 30
        )

        # ─── Phase 4 + 5 : Collecte et structuration ───
        for i, product_info in enumerate(products):
            product_name = product_info["name"]
            brand = product_info.get("brand", "")
            search_query = product_info.get("search_query", f"{product_name} prix avis")
            progress = 30 + int((i / total_products) * 55)

            update_benchmark_status(
                benchmark_id, "collecting",
                f"Phase 4 : Collecte de {product_name} ({i+1}/{total_products})...",
                progress
            )

            print(f"[BENCHMARK] Collecte de {product_name}...")

            # Scraping multi-requêtes
            scrape_result = _scrape_with_multiple_queries(
                product_name, brand, search_query
            )

            print(f"[BENCHMARK] {product_name}: {scrape_result['urls_tried']} URLs testées, "
                  f"{len(scrape_result['text'])} caractères collectés")

            # Structurer les données scrapées
            extracted = {}
            completeness = 0.0

            if scrape_result["text"]:
                try:
                    structured = structure_scraped_data(product_name, scrape_result["text"], criteria)
                    extracted = structured.get("extracted", {})
                    completeness = structured.get("completeness", 0.0)
                    print(f"[BENCHMARK] {product_name}: extraction OK, complétude {completeness:.0%}")
                except Exception as e:
                    print(f"[BENCHMARK] {product_name}: erreur extraction - {e}")

            # FALLBACK : enrichir avec les connaissances de l'IA si données insuffisantes
            if completeness < 0.5:
                print(f"[BENCHMARK] {product_name}: enrichissement IA (complétude faible: {completeness:.0%})")
                try:
                    extracted = enrich_product_from_knowledge(product_name, criteria, extracted)
                    # Recalculer la complétude
                    filled = sum(1 for v in extracted.values() if v is not None)
                    completeness = filled / max(total_fields, 1)
                    print(f"[BENCHMARK] {product_name}: après enrichissement, complétude {completeness:.0%}")
                except Exception as e:
                    print(f"[BENCHMARK] {product_name}: erreur enrichissement - {e}")

            # Extraire le prix
            price_min = None
            price_max = None
            for key, val in extracted.items():
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

            # Si pas de prix trouvé dans les données, utiliser le prix estimé de la sélection
            if price_min is None and product_info.get("estimated_price"):
                price_min = product_info["estimated_price"]
                price_max = product_info["estimated_price"]

            # Sauvegarder
            product_data = {
                "id": str(uuid.uuid4()),
                "name": product_name,
                "brand": brand,
                "image_url": scrape_result["image_url"],
                "source_url": scrape_result["source_url"],
                "price_min": price_min,
                "price_max": price_max,
                "data": extracted,
                "completeness": completeness,
            }
            save_product(benchmark_id, product_data)

        # ─── Phase 6 : Terminé ───
        update_benchmark_status(
            benchmark_id, "done",
            f"Benchmark terminé ! {total_products} produits collectés.", 100
        )
        print(f"[BENCHMARK] Terminé avec succès : {total_products} produits")

    except Exception as e:
        print(f"[BENCHMARK] ERREUR : {e}")
        update_benchmark_status(
            benchmark_id, "error",
            f"Erreur : {str(e)}", 0
        )
        raise
