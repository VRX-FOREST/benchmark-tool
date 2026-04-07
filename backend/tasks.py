"""
tasks.py — Deep Research Benchmark V3.

La qualité prime sur tout. Le temps n'est PAS un critère.
Chaque produit fait l'objet d'une collecte exhaustive :
  - Recherche multi-stratégies (7 angles différents)
  - Validation de chaque page (est-ce bien le produit ?)
  - Extraction + ré-extraction sur les champs manquants
  - Croisement des sources
  - Image validée depuis la page produit confirmée
"""
import uuid
import asyncio
from celery_app import celery
from database import (
    init_db,
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
from scraper import deep_search_product

init_db()


def _run_async(coro):
    """Helper pour exécuter du code async dans Celery."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _count_completeness(data: dict, total_fields: int) -> float:
    if total_fields == 0:
        return 0.0
    filled = sum(1 for v in data.values() if v is not None)
    return filled / total_fields


def _select_best_image(pages: list[dict]) -> str:
    """
    Sélectionne la meilleure image produit parmi toutes les pages collectées.
    Priorité : page produit confirmée > og:image > grande image.
    """
    # Priorité 1 : images des pages produit confirmées
    for page in pages:
        if page.get("is_product_page") and page.get("images"):
            for img in page["images"]:
                if img.get("priority", 99) <= 2 and img.get("url"):
                    return img["url"]

    # Priorité 2 : n'importe quelle og:image
    for page in pages:
        if page.get("images"):
            for img in page["images"]:
                if img.get("source") in ("og:image", "json-ld") and img.get("url"):
                    return img["url"]

    # Priorité 3 : première image trouvée
    for page in pages:
        if page.get("image_url"):
            return page["image_url"]

    return ""


def _select_best_source_url(pages: list[dict]) -> str:
    """
    Sélectionne la meilleure URL source pour le produit.
    Priorité : page produit confirmée sur site fiable.
    """
    priority_domains = [
        "amazon.fr", "fnac.com", "decathlon.fr", "boulanger.com",
        "darty.com", "cdiscount.com",
    ]

    # Priorité 1 : page produit confirmée sur site prioritaire
    for page in pages:
        if page.get("is_product_page"):
            url = page.get("url", "")
            if any(d in url for d in priority_domains):
                return url

    # Priorité 2 : n'importe quelle page produit confirmée
    for page in pages:
        if page.get("is_product_page"):
            return page.get("url", "")

    # Priorité 3 : première page avec du contenu
    for page in pages:
        if page.get("url"):
            return page["url"]

    return ""


@celery.task(bind=True, name="run_benchmark")
def run_benchmark(self, benchmark_id: str, product_type: str, config: dict):
    """
    Deep Research Benchmark — qualité maximale, pas de compromis sur le temps.
    """
    try:
        # ─── Phase préliminaire : Analyse du marché ───
        update_benchmark_status(
            benchmark_id, "selecting",
            "Analyse préliminaire du marché en cours...", 3
        )
        print(f"\n[BENCHMARK] ══════════════════════════════════════")
        print(f"[BENCHMARK] Démarrage : {product_type}")
        print(f"[BENCHMARK] ══════════════════════════════════════")

        market_research = research_market_landscape(product_type, config)
        segments = market_research.get("segments", [])
        brands = market_research.get("leading_brands", [])
        print(f"[BENCHMARK] Marché analysé : {len(segments)} segments, {len(brands)} marques")

        # ─── Phase 2 : Sélection des produits ───
        update_benchmark_status(
            benchmark_id, "selecting",
            f"Sélection des produits ({len(brands)} marques identifiées)...", 8
        )

        products = select_products(product_type, config, market_research)
        total_products = len(products)

        if not products:
            update_benchmark_status(benchmark_id, "error", "Aucun produit trouvé.", 0)
            return

        for p in products:
            print(f"[BENCHMARK]   → {p['name']} ({p.get('segment', '?')}) - {p.get('why_selected', '')}")

        # ─── Phase 3 : Critères de comparaison ───
        update_benchmark_status(
            benchmark_id, "criteria",
            "Définition des critères de comparaison professionnels...", 12
        )

        criteria = define_criteria(product_type, market_research)
        update_benchmark_criteria(benchmark_id, criteria)

        total_fields = sum(len(cat.get("fields", [])) for cat in criteria)
        print(f"[BENCHMARK] {total_fields} critères en {len(criteria)} catégories")

        # ─── Phase 4+5 : Collecte approfondie produit par produit ───
        for i, product_info in enumerate(products):
            product_name = product_info["name"]
            brand = product_info.get("brand", "")
            progress = 15 + int((i / total_products) * 75)

            update_benchmark_status(
                benchmark_id, "collecting",
                f"Collecte approfondie : {product_name} ({i+1}/{total_products})...",
                progress
            )

            print(f"\n[BENCHMARK] ═══ Produit {i+1}/{total_products} : {product_name} ═══")

            # ── Étape 1 : Collecte multi-sources ──
            pages = _run_async(deep_search_product(product_name, brand))

            # ── Étape 2 : Sélection de la meilleure image et source ──
            image_url = _select_best_image(pages)
            source_url = _select_best_source_url(pages)

            product_pages = [p for p in pages if p.get("is_product_page")]
            other_pages = [p for p in pages if not p.get("is_product_page")]

            print(f"  [COLLECT] {len(product_pages)} pages produit confirmées, "
                  f"{len(other_pages)} autres sources")
            print(f"  [COLLECT] Image : {'✓' if image_url else '✗'}")
            print(f"  [COLLECT] Source : {source_url or '(aucune)'}")

            # ── Étape 3 : Première extraction (toutes les sources combinées) ──
            combined_text = ""
            all_source_urls = []
            for page in pages:
                combined_text += f"\n\n══ Source: {page['url']} ({page.get('source_type', 'web')}) ══\n"
                combined_text += page.get("text", "")
                all_source_urls.append(page["url"])

            extracted_data = {}
            sources_per_field = {}
            completeness = 0.0

            if combined_text:
                try:
                    result = structure_scraped_data(
                        product_name, combined_text, criteria, all_source_urls
                    )
                    extracted_data = result.get("extracted", {})
                    sources_per_field = result.get("sources_per_field", {})
                    completeness = _count_completeness(extracted_data, total_fields)
                    print(f"  [EXTRACT] Extraction 1 : {completeness:.0%} complétude")
                except Exception as e:
                    print(f"  [EXTRACT] Erreur extraction 1 : {e}")

            # ── Étape 4 : Si des pages produit existent mais pas encore exploitées ──
            if completeness < 0.65 and product_pages:
                print(f"  [EXTRACT] Ré-extraction ciblée sur les pages produit confirmées...")
                product_text = ""
                product_urls = []
                for page in product_pages:
                    product_text += f"\n\n══ Source: {page['url']} ══\n{page.get('text', '')}"
                    product_urls.append(page["url"])

                try:
                    extracted_data, new_sources = deep_extract_missing_fields(
                        product_name, criteria, extracted_data, product_text, product_urls
                    )
                    sources_per_field.update(new_sources)
                    completeness = _count_completeness(extracted_data, total_fields)
                    print(f"  [EXTRACT] Après ré-extraction : {completeness:.0%}")
                except Exception as e:
                    print(f"  [EXTRACT] Erreur ré-extraction : {e}")

            # ── Étape 5 : Enrichissement IA (dernier recours) ──
            if completeness < 0.45:
                print(f"  [EXTRACT] Enrichissement IA (complétude basse : {completeness:.0%})...")
                try:
                    extracted_data = enrich_product_from_knowledge(
                        product_name, criteria, extracted_data
                    )
                    completeness = _count_completeness(extracted_data, total_fields)
                    print(f"  [EXTRACT] Après enrichissement IA : {completeness:.0%}")
                except Exception as e:
                    print(f"  [EXTRACT] Erreur enrichissement : {e}")

            # ── Étape 6 : Extraction du prix ──
            price_min = None
            price_max = None
            for key, val in extracted_data.items():
                if "prix" in key.lower() and val is not None:
                    try:
                        price_str = str(val).replace("€", "").replace(",", ".").replace("\u00a0", "").replace(" ", "").strip()
                        price_val = float(price_str)
                        if price_min is None or price_val < price_min:
                            price_min = price_val
                        if price_max is None or price_val > price_max:
                            price_max = price_val
                    except (ValueError, TypeError):
                        pass

            if price_min is None and product_info.get("estimated_price"):
                price_min = product_info["estimated_price"]
                price_max = product_info["estimated_price"]

            # ── Étape 7 : Sauvegarde ──
            source_summary = [
                {"url": p["url"], "type": p.get("source_type", "web"), 
                 "is_product_page": p.get("is_product_page", False)}
                for p in pages
            ]

            product_data = {
                "id": str(uuid.uuid4()),
                "name": product_name,
                "brand": brand,
                "image_url": image_url,
                "source_url": source_url,
                "price_min": price_min,
                "price_max": price_max,
                "data": extracted_data,
                "completeness": completeness,
                "sources": source_summary,
                "sources_per_field": sources_per_field,
            }
            save_product(benchmark_id, product_data)

            print(f"  [SAVE] ✓ {product_name} sauvegardé — "
                  f"{completeness:.0%} complétude, "
                  f"{len(source_summary)} sources, "
                  f"prix: {price_min or '?'}€")

        # ─── Terminé ───
        update_benchmark_status(
            benchmark_id, "done",
            f"Benchmark terminé ! {total_products} produits collectés en profondeur.", 100
        )
        print(f"\n[BENCHMARK] ══════════════════════════════════════")
        print(f"[BENCHMARK] TERMINÉ : {total_products} produits")
        print(f"[BENCHMARK] ══════════════════════════════════════")

    except Exception as e:
        print(f"\n[BENCHMARK] ❌ ERREUR FATALE : {e}")
        import traceback
        traceback.print_exc()
        update_benchmark_status(
            benchmark_id, "error",
            f"Erreur : {str(e)}", 0
        )
        raise
