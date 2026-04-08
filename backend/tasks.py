"""
tasks.py — Deep Research Benchmark V6.

Deux tâches Celery :
1. discover_products_task : trouve les produits candidats (rapide, avec photo/prix/lien)
2. run_benchmark : deep research sur les produits sélectionnés par l'utilisateur
"""
import uuid
from celery_app import celery
from database import (
    init_db,
    update_benchmark_status, update_benchmark_criteria,
    save_product, save_candidates,
)
from agent import (
    research_market_landscape,
    select_products,
    define_criteria,
    structure_scraped_data,
    deep_extract_missing_fields,
    enrich_product_from_knowledge,
)
from scraper import (
    deep_collect_product,
    find_product_url,
    find_product_image,
    _openai_web_search,
)

init_db()


def _count_completeness(data: dict, total_fields: int) -> float:
    if total_fields == 0:
        return 0.0
    filled = sum(1 for v in data.values() if v is not None)
    return filled / total_fields


# ══════════════════════════════════════════════
# TÂCHE 1 : DÉCOUVERTE DES PRODUITS CANDIDATS
# ══════════════════════════════════════════════

@celery.task(bind=True, name="discover_products")
def discover_products_task(self, benchmark_id: str, product_type: str, config: dict):
    """
    Phase 1 : Trouve les produits candidats avec photo, prix et lien.
    Rapide : on cherche juste l'essentiel pour que l'utilisateur puisse choisir.
    """
    try:
        update_benchmark_status(
            benchmark_id, "discovering",
            "Analyse du marché en cours...", 5
        )
        print(f"\n[DISCOVER] ══════════════════════════════════════")
        print(f"[DISCOVER] Recherche de produits : {product_type}")
        print(f"[DISCOVER] ══════════════════════════════════════")

        # Analyse du marché
        market_research = research_market_landscape(product_type, config)
        print(f"[DISCOVER] Marché analysé")

        update_benchmark_status(
            benchmark_id, "discovering",
            "Sélection des produits candidats...", 15
        )

        # Sélection des produits
        products = select_products(product_type, config, market_research)
        total = len(products)
        print(f"[DISCOVER] {total} produits identifiés")

        if not products:
            update_benchmark_status(benchmark_id, "error", "Aucun produit trouvé.", 0)
            return

        # Pour chaque produit : trouver prix, lien et photo
        candidates = []
        for i, p in enumerate(products):
            name = p["name"]
            brand = p.get("brand", "")
            progress = 15 + int((i / total) * 80)

            update_benchmark_status(
                benchmark_id, "discovering",
                f"Recherche de {name} ({i+1}/{total})...", progress
            )

            print(f"\n[DISCOVER] ── {i+1}/{total} : {name} ──")

            # Trouver le lien
            source_url = find_product_url(name, brand)

            # Trouver l'image
            image_url = find_product_image(name, brand, source_url)

            # Prix estimé (depuis la sélection IA ou recherche rapide)
            estimated_price = p.get("estimated_price")
            if not estimated_price:
                # Recherche rapide du prix
                price_result = _openai_web_search(f"prix {name} en France euros")
                if price_result["success"]:
                    import re
                    prices = re.findall(r'(\d+[.,]?\d*)\s*€', price_result["text"])
                    if prices:
                        try:
                            estimated_price = float(prices[0].replace(",", "."))
                        except:
                            pass

            candidate = {
                "id": str(uuid.uuid4()),
                "name": name,
                "brand": brand,
                "segment": p.get("segment", ""),
                "estimated_price": estimated_price,
                "why_selected": p.get("why_selected", ""),
                "image_url": image_url or "",
                "source_url": source_url or "",
                "selected": True,  # Pré-sélectionné par défaut
            }
            candidates.append(candidate)

            status_icon = f"{'✓' if source_url else '✗'} lien | {'✓' if image_url else '✗'} image | {'✓' if estimated_price else '✗'} prix"
            print(f"[DISCOVER] {status_icon}")

        # Sauvegarder les candidats dans la base
        save_candidates(benchmark_id, candidates)

        # Stocker aussi l'analyse de marché pour la phase 2
        from database import save_market_research
        save_market_research(benchmark_id, market_research)

        update_benchmark_status(
            benchmark_id, "selection",
            f"{total} produits trouvés. Sélectionnez ceux à benchmarker.", 100
        )

        print(f"\n[DISCOVER] ══════════════════════════════════════")
        print(f"[DISCOVER] TERMINÉ : {total} candidats avec photos et liens")
        print(f"[DISCOVER] ══════════════════════════════════════")

    except Exception as e:
        print(f"\n[DISCOVER] ❌ ERREUR : {e}")
        import traceback
        traceback.print_exc()
        update_benchmark_status(benchmark_id, "error", f"Erreur : {str(e)}", 0)
        raise


# ══════════════════════════════════════════════
# TÂCHE 2 : DEEP RESEARCH (produits sélectionnés)
# ══════════════════════════════════════════════

@celery.task(bind=True, name="run_benchmark")
def run_benchmark(self, benchmark_id: str, product_type: str, config: dict, selected_products: list = None):
    """
    Phase 2 : Deep research sur les produits sélectionnés par l'utilisateur.
    Si selected_products est None, fait la sélection automatique (mode legacy).
    """
    try:
        # ─── Si pas de produits présélectionnés, mode legacy ───
        if selected_products is None:
            market_research = research_market_landscape(product_type, config)
            selected_products_raw = select_products(product_type, config, market_research)
            selected_products = [
                {"name": p["name"], "brand": p.get("brand", ""), 
                 "image_url": "", "source_url": "", "estimated_price": p.get("estimated_price")}
                for p in selected_products_raw
            ]
            market_research_data = market_research
        else:
            # Récupérer l'analyse de marché sauvegardée
            from database import get_market_research
            market_research_data = get_market_research(benchmark_id)

        total_products = len(selected_products)
        if not total_products:
            update_benchmark_status(benchmark_id, "error", "Aucun produit sélectionné.", 0)
            return

        print(f"\n[BENCHMARK] ══════════════════════════════════════")
        print(f"[BENCHMARK] Deep Research : {product_type}")
        print(f"[BENCHMARK] {total_products} produits sélectionnés")
        print(f"[BENCHMARK] ══════════════════════════════════════")

        # ─── Critères de comparaison ───
        update_benchmark_status(
            benchmark_id, "criteria",
            "Définition des critères de comparaison...", 10
        )

        criteria = define_criteria(product_type, market_research_data)
        update_benchmark_criteria(benchmark_id, criteria)

        total_fields = sum(len(cat.get("fields", [])) for cat in criteria)
        print(f"[BENCHMARK] {total_fields} critères en {len(criteria)} catégories")

        criteria_summary = ""
        for cat in criteria:
            field_names = [f["name"] for f in cat.get("fields", [])]
            criteria_summary += f"{cat['category']}: {', '.join(field_names)}\n"

        # ─── Collecte produit par produit ───
        for i, product_info in enumerate(selected_products):
            product_name = product_info["name"]
            brand = product_info.get("brand", "")
            progress = 15 + int((i / total_products) * 75)

            update_benchmark_status(
                benchmark_id, "collecting",
                f"Collecte approfondie : {product_name} ({i+1}/{total_products})...",
                progress
            )

            print(f"\n[BENCHMARK] ═══ Produit {i+1}/{total_products} : {product_name} ═══")

            # Utiliser le lien/image déjà trouvés en phase 1 si disponibles
            existing_source = product_info.get("source_url", "")
            existing_image = product_info.get("image_url", "")

            # Collecte des données
            collected = deep_collect_product(product_name, brand, criteria_summary)

            # Priorité aux liens/images déjà validés en phase 1
            image_url = existing_image or collected["image_url"]
            source_url = existing_source or collected["best_source_url"]

            # Extraction des données
            extracted_data = {}
            sources_per_field = {}
            completeness = 0.0

            if collected["text"]:
                try:
                    result = structure_scraped_data(
                        product_name, collected["text"], criteria, collected["source_urls"]
                    )
                    extracted_data = result.get("extracted", {})
                    sources_per_field = result.get("sources_per_field", {})
                    completeness = _count_completeness(extracted_data, total_fields)
                    print(f"  [EXTRACT] Extraction 1 : {completeness:.0%}")
                except Exception as e:
                    print(f"  [EXTRACT] Erreur : {e}")

            # Recherche complémentaire ciblée
            if completeness < 0.60:
                missing_by_cat = {}
                for cat in criteria:
                    for field in cat.get("fields", []):
                        unit_str = f" ({field['unit']})" if field.get("unit") else ""
                        key = f"{cat['category']} > {field['name']}{unit_str}"
                        if extracted_data.get(key) is None:
                            if cat["category"] not in missing_by_cat:
                                missing_by_cat[cat["category"]] = []
                            missing_by_cat[cat["category"]].append(field["name"])

                for cat_name, missing_fields in missing_by_cat.items():
                    fields_str = ", ".join(missing_fields[:5])
                    print(f"  [EXTRACT] Recherche ciblée : {cat_name}")

                    targeted = _openai_web_search(
                        f"Pour le produit {product_name} ({brand}), "
                        f"trouve : {fields_str}. "
                        f"Donne des valeurs PRÉCISES avec sources."
                    )

                    if targeted["success"] and targeted["text"]:
                        new_urls = [s["url"] for s in targeted["sources"]]
                        try:
                            extracted_data, new_sources = deep_extract_missing_fields(
                                product_name, criteria, extracted_data,
                                targeted["text"], new_urls
                            )
                            sources_per_field.update(new_sources)
                            completeness = _count_completeness(extracted_data, total_fields)
                        except Exception as e:
                            print(f"  [EXTRACT] Erreur ciblée : {e}")

            # Enrichissement IA
            if completeness < 0.40:
                try:
                    extracted_data = enrich_product_from_knowledge(
                        product_name, criteria, extracted_data
                    )
                    completeness = _count_completeness(extracted_data, total_fields)
                except Exception as e:
                    print(f"  [EXTRACT] Erreur enrichissement : {e}")

            # Prix
            price_min = None
            price_max = None
            for key, val in extracted_data.items():
                if "prix" in key.lower() and val is not None:
                    try:
                        price_str = str(val).replace("€", "").replace(",", ".").replace("\u00a0", "").replace(" ", "")
                        price_val = float(price_str)
                        if price_min is None or price_val < price_min:
                            price_min = price_val
                        if price_max is None or price_val > price_max:
                            price_max = price_val
                    except:
                        pass

            if price_min is None and product_info.get("estimated_price"):
                price_min = product_info["estimated_price"]
                price_max = product_info["estimated_price"]

            # Sauvegarde
            source_summary = [{"url": s["url"], "title": s.get("title", "")} for s in collected["sources"]]

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

            print(f"  [SAVE] ✓ {product_name} — {completeness:.0%}, "
                  f"image: {'✓' if image_url else '✗'}, lien: {'✓' if source_url else '✗'}")

        # Terminé
        update_benchmark_status(
            benchmark_id, "done",
            f"Benchmark terminé ! {total_products} produits.", 100
        )
        print(f"\n[BENCHMARK] TERMINÉ : {total_products} produits")

    except Exception as e:
        print(f"\n[BENCHMARK] ❌ ERREUR : {e}")
        import traceback
        traceback.print_exc()
        update_benchmark_status(benchmark_id, "error", f"Erreur : {str(e)}", 0)
        raise
