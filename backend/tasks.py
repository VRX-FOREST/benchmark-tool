"""
tasks.py — Tâches Celery exécutées en arrière-plan.
C'est ici que se déroule le vrai travail : sélection des produits,
collecte web, structuration des données.
"""
import uuid
import asyncio
from celery_app import celery
from database import (
    update_benchmark_status, update_benchmark_criteria,
    save_product, get_benchmark
)
from agent import select_products, define_criteria, structure_scraped_data, search_product_urls
from scraper import scrape_product, search_web


def _run_async(coro):
    """Helper pour exécuter du code async dans Celery (qui est synchrone)."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery.task(bind=True, name="run_benchmark")
def run_benchmark(self, benchmark_id: str, product_type: str, config: dict):
    """
    Tâche principale : exécute les 6 phases du benchmark.
    Met à jour la progression en base à chaque étape.
    """
    try:
        # ─── Phase 2 : Sélection des produits ───
        update_benchmark_status(
            benchmark_id, "selecting",
            "Phase 2 : Sélection des produits à comparer...", 10
        )

        products = select_products(product_type, config)
        total_products = len(products)

        if not products:
            update_benchmark_status(benchmark_id, "error", "Aucun produit trouvé.", 0)
            return

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

        update_benchmark_status(
            benchmark_id, "criteria",
            f"Critères définis. Lancement de la collecte pour {total_products} produits...", 30
        )

        # ─── Phase 4 : Collecte des données ───
        for i, product_info in enumerate(products):
            product_name = product_info["name"]
            progress = 30 + int((i / total_products) * 50)

            update_benchmark_status(
                benchmark_id, "collecting",
                f"Phase 4 : Collecte de {product_name} ({i+1}/{total_products})...",
                progress
            )

            # Chercher les URLs à scraper
            search_results = _run_async(
                search_web(f"{product_name} fiche technique prix avis", num_results=5)
            )

            # Si pas de résultats ScraperAPI, utiliser l'IA pour deviner les URLs
            if not search_results:
                url_suggestions = search_product_urls(product_name, config.get("market", "France"))
                search_results = [{"url": u["url"], "title": "", "snippet": ""} for u in url_suggestions[:3]]

            # Scraper les pages trouvées et collecter les données
            all_text = ""
            image_url = ""
            source_url = ""

            for result in search_results[:3]:  # Max 3 pages par produit
                url = result.get("url", "")
                if not url:
                    continue

                page_data = _run_async(scrape_product(url))
                if page_data.get("success"):
                    all_text += f"\n\n--- Source: {url} ---\n{page_data['text']}"
                    if not image_url and page_data.get("image_url"):
                        image_url = page_data["image_url"]
                    if not source_url:
                        source_url = url

            # ─── Phase 5 : Structuration des données ───
            if all_text:
                structured = structure_scraped_data(product_name, all_text, criteria)
                extracted = structured.get("extracted", {})
                completeness = structured.get("completeness", 0.0)
            else:
                extracted = {}
                completeness = 0.0

            # Extraire le prix si disponible
            price_min = None
            price_max = None
            for key, val in extracted.items():
                if "prix" in key.lower() and val is not None:
                    try:
                        price_val = float(str(val).replace("€", "").replace(",", ".").strip())
                        if price_min is None or price_val < price_min:
                            price_min = price_val
                        if price_max is None or price_val > price_max:
                            price_max = price_val
                    except (ValueError, TypeError):
                        pass

            # Sauvegarder le produit
            product_data = {
                "id": str(uuid.uuid4()),
                "name": product_name,
                "brand": product_info.get("brand", ""),
                "image_url": image_url,
                "source_url": source_url,
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

    except Exception as e:
        update_benchmark_status(
            benchmark_id, "error",
            f"Erreur : {str(e)}", 0
        )
        raise
