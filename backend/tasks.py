"""
tasks.py — Deep Research Benchmark V5.

Source principale : OpenAI web search (zéro coût supplémentaire).
Lien source et image OBLIGATOIRES pour chaque produit.
"""
import uuid
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
from scraper import deep_collect_product, _openai_web_search

init_db()


def _count_completeness(data: dict, total_fields: int) -> float:
    if total_fields == 0:
        return 0.0
    filled = sum(1 for v in data.values() if v is not None)
    return filled / total_fields


@celery.task(bind=True, name="run_benchmark")
def run_benchmark(self, benchmark_id: str, product_type: str, config: dict):
    """
    Deep Research Benchmark V5.
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
            print(f"[BENCHMARK]   → {p['name']} ({p.get('segment', '?')})")

        # ─── Phase 3 : Critères de comparaison ───
        update_benchmark_status(
            benchmark_id, "criteria",
            "Définition des critères de comparaison professionnels...", 12
        )

        criteria = define_criteria(product_type, market_research)
        update_benchmark_criteria(benchmark_id, criteria)

        total_fields = sum(len(cat.get("fields", [])) for cat in criteria)
        print(f"[BENCHMARK] {total_fields} critères en {len(criteria)} catégories")

        # Résumé des critères pour le scraper
        criteria_summary = ""
        for cat in criteria:
            field_names = [f["name"] for f in cat.get("fields", [])]
            criteria_summary += f"{cat['category']}: {', '.join(field_names)}\n"

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

            # ── Étape 1 : Collecte combinée ──
            collected = deep_collect_product(product_name, brand, criteria_summary)

            image_url = collected["image_url"]
            best_source_url = collected["best_source_url"]
            all_sources = collected["sources"]
            source_urls = collected["source_urls"]

            # ── Étape 2 : Extraction des données structurées ──
            extracted_data = {}
            sources_per_field = {}
            completeness = 0.0

            if collected["text"]:
                print(f"  [EXTRACT] Extraction des données depuis {len(source_urls)} sources...")
                try:
                    result = structure_scraped_data(
                        product_name, collected["text"], criteria, source_urls
                    )
                    extracted_data = result.get("extracted", {})
                    sources_per_field = result.get("sources_per_field", {})
                    completeness = _count_completeness(extracted_data, total_fields)
                    print(f"  [EXTRACT] Extraction 1 : {completeness:.0%} complétude")
                except Exception as e:
                    print(f"  [EXTRACT] Erreur extraction : {e}")

            # ── Étape 3 : Recherche complémentaire ciblée si complétude insuffisante ──
            if completeness < 0.60:
                print(f"  [EXTRACT] Complétude faible ({completeness:.0%}), recherche complémentaire...")

                # Identifier les champs manquants par catégorie
                missing_by_cat = {}
                for cat in criteria:
                    for field in cat.get("fields", []):
                        unit_str = f" ({field['unit']})" if field.get("unit") else ""
                        key = f"{cat['category']} > {field['name']}{unit_str}"
                        if extracted_data.get(key) is None:
                            if cat["category"] not in missing_by_cat:
                                missing_by_cat[cat["category"]] = []
                            missing_by_cat[cat["category"]].append(field["name"])

                # Recherche ciblée sur les catégories manquantes
                for cat_name, missing_fields in missing_by_cat.items():
                    fields_str = ", ".join(missing_fields[:5])
                    print(f"  [EXTRACT] Recherche ciblée : {cat_name} ({len(missing_fields)} champs)")

                    targeted = _openai_web_search(
                        f"Pour le produit {product_name} ({brand}), "
                        f"trouve spécifiquement ces informations : {fields_str}. "
                        f"Catégorie : {cat_name}. "
                        f"Cherche sur les fiches techniques, tests, et sites marchands français. "
                        f"Donne des valeurs PRÉCISES avec les sources."
                    )

                    if targeted["success"] and targeted["text"]:
                        new_urls = [s["url"] for s in targeted["sources"]]
                        try:
                            extracted_data, new_field_sources = deep_extract_missing_fields(
                                product_name, criteria, extracted_data,
                                targeted["text"], new_urls
                            )
                            sources_per_field.update(new_field_sources)
                            completeness = _count_completeness(extracted_data, total_fields)
                            print(f"  [EXTRACT] Après recherche ciblée {cat_name} : {completeness:.0%}")
                        except Exception as e:
                            print(f"  [EXTRACT] Erreur extraction ciblée : {e}")

                    # Ajouter les nouvelles sources
                    for s in targeted.get("sources", []):
                        if s["url"] not in [x["url"] for x in all_sources]:
                            all_sources.append(s)

            # ── Étape 4 : Enrichissement IA (dernier recours) ──
            if completeness < 0.40:
                print(f"  [EXTRACT] Enrichissement IA (complétude {completeness:.0%})...")
                try:
                    extracted_data = enrich_product_from_knowledge(
                        product_name, criteria, extracted_data
                    )
                    completeness = _count_completeness(extracted_data, total_fields)
                    print(f"  [EXTRACT] Après enrichissement IA : {completeness:.0%}")
                except Exception as e:
                    print(f"  [EXTRACT] Erreur enrichissement : {e}")

            # ── Étape 5 : Prix ──
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

            # ── Étape 6 : Vérification finale lien + image ──
            if not best_source_url:
                print(f"  [WARNING] ⚠ Pas de lien source pour {product_name}")
            if not image_url:
                print(f"  [WARNING] ⚠ Pas d'image pour {product_name}")

            # ── Étape 7 : Sauvegarde ──
            source_summary = [
                {"url": s["url"], "title": s.get("title", "")}
                for s in all_sources
            ]

            product_data = {
                "id": str(uuid.uuid4()),
                "name": product_name,
                "brand": brand,
                "image_url": image_url,
                "source_url": best_source_url,
                "price_min": price_min,
                "price_max": price_max,
                "data": extracted_data,
                "completeness": completeness,
                "sources": source_summary,
                "sources_per_field": sources_per_field,
            }
            save_product(benchmark_id, product_data)

            print(f"  [SAVE] ✓ {product_name} — "
                  f"{completeness:.0%} complétude, "
                  f"{len(source_summary)} sources, "
                  f"prix: {price_min or '?'}€, "
                  f"image: {'✓' if image_url else '✗'}, "
                  f"lien: {'✓' if best_source_url else '✗'}")

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
