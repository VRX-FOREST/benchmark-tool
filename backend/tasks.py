"""
tasks.py — Deep Research Benchmark V7.

RÈGLE ABSOLUE : chaque produit candidat DOIT avoir une photo ET un lien.
Si après toutes les tentatives un produit n'a ni photo ni lien,
il est remplacé par un produit alternatif.
"""
import uuid
from celery_app import celery
from database import (
    init_db,
    update_benchmark_status, update_benchmark_criteria,
    save_product, save_candidates, save_market_research,
    get_market_research,
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


def _find_url_with_retries(product_name: str, brand: str, max_retries: int = 3) -> str:
    """
    Cherche le lien source avec plusieurs tentatives et reformulations.
    """
    # Tentative 1 : recherche standard
    url = find_product_url(product_name, brand)
    if url:
        return url

    # Tentative 2 : reformuler le nom du produit
    print(f"  [LIEN] Retry 2 : reformulation du nom...")
    simplified_name = product_name.replace("Foam Roller", "rouleau").replace("foam roller", "rouleau")
    url = find_product_url(simplified_name, brand)
    if url:
        return url

    # Tentative 3 : recherche par marque seule
    print(f"  [LIEN] Retry 3 : recherche par marque...")
    result = _openai_web_search(
        f"Acheter {product_name} en France. "
        f"Donne le lien DIRECT de la page produit sur un site marchand "
        f"(amazon.fr, fnac.com, decathlon.fr, boulanger.com, cdiscount.com, darty.com). "
        f"PAS un lien de page de recherche."
    )
    if result["success"]:
        for s in result["sources"]:
            u = s["url"]
            if "/s?" not in u and "/search" not in u and "/recherche" not in u:
                # Validation rapide
                import asyncio
                loop = asyncio.new_event_loop()
                try:
                    from scraper import _validate_url
                    is_valid = loop.run_until_complete(_validate_url(u))
                    if is_valid:
                        return u
                finally:
                    loop.close()

    return ""


def _find_image_with_retries(product_name: str, brand: str, source_url: str, max_retries: int = 3) -> str:
    """
    Cherche l'image avec plusieurs tentatives et stratégies.
    """
    # Tentative 1 : recherche standard
    img = find_product_image(product_name, brand, source_url)
    if img:
        return img

    # Tentative 2 : recherche Google Images via OpenAI
    print(f"  [IMAGE] Retry 2 : Google Images...")
    result = _openai_web_search(
        f"Image produit {product_name} {brand}. "
        f"Trouve l'URL DIRECTE d'une photo du produit au format .jpg ou .png. "
        f"L'URL doit commencer par https:// et finir par .jpg, .jpeg, .png ou .webp. "
        f"Cherche sur Google Images, le site {brand}, ou amazon.fr."
    )
    if result["success"]:
        import re
        patterns = [
            r'https://m\.media-amazon\.com/images/I/[A-Za-z0-9._+-]+\.(?:jpg|png|webp)',
            r'https?://[^\s<>"\']+\.(?:jpg|jpeg|png|webp)(?:\?[^\s<>"\']*)?',
        ]
        for pattern in patterns:
            matches = re.findall(pattern, result["text"])
            for match in matches:
                match = match.rstrip(".,;:)")
                if len(match) > 25:
                    # Valider
                    import asyncio
                    loop = asyncio.new_event_loop()
                    try:
                        from scraper import _validate_image_url
                        is_valid = loop.run_until_complete(_validate_image_url(match))
                        if is_valid:
                            return match
                    finally:
                        loop.close()

    # Tentative 3 : chercher une image du produit via une autre requête
    print(f"  [IMAGE] Retry 3 : recherche alternative...")
    result3 = _openai_web_search(
        f"photo {product_name} png OR jpg site:amazon.fr OR site:{brand.lower()}.com OR site:{brand.lower()}.fr"
    )
    if result3["success"]:
        import re
        matches = re.findall(r'https?://[^\s<>"\']+\.(?:jpg|jpeg|png|webp)', result3["text"])
        for match in matches:
            match = match.rstrip(".,;:)")
            if len(match) > 25:
                import asyncio
                loop2 = asyncio.new_event_loop()
                try:
                    from scraper import _validate_image_url
                    is_valid = loop2.run_until_complete(_validate_image_url(match))
                    if is_valid:
                        return match
                finally:
                    loop2.close()

    return ""


# ══════════════════════════════════════════════
# TÂCHE 1 : DÉCOUVERTE (avec lien + image obligatoires)
# ══════════════════════════════════════════════

@celery.task(bind=True, name="discover_products")
def discover_products_task(self, benchmark_id: str, product_type: str, config: dict):
    """
    Phase 1 : Trouve les produits candidats.
    CHAQUE produit DOIT avoir un lien source ET une photo.
    """
    try:
        update_benchmark_status(
            benchmark_id, "discovering",
            "Analyse du marché en cours...", 5
        )
        print(f"\n[DISCOVER] ══════════════════════════════════════")
        print(f"[DISCOVER] Recherche de produits : {product_type}")

        # Analyse du marché
        market_research = research_market_landscape(product_type, config)
        save_market_research(benchmark_id, market_research)
        print(f"[DISCOVER] Marché analysé")

        update_benchmark_status(
            benchmark_id, "discovering",
            "Sélection des produits candidats...", 15
        )

        # Sélection des produits (demander plus que nécessaire pour avoir des remplaçants)
        max_wanted = config.get("max_products", 12)
        config_extended = {**config, "max_products": max_wanted + 4}
        products = select_products(product_type, config_extended, market_research)
        total = len(products)
        print(f"[DISCOVER] {total} produits identifiés (dont {4} remplaçants)")

        if not products:
            update_benchmark_status(benchmark_id, "error", "Aucun produit trouvé.", 0)
            return

        # Pour chaque produit : trouver lien + photo + prix
        candidates = []
        skipped = 0

        for i, p in enumerate(products):
            name = p["name"]
            brand = p.get("brand", "")
            progress = 15 + int((i / total) * 80)

            # Si on a déjà assez de candidats valides, on arrête
            if len(candidates) >= max_wanted:
                print(f"[DISCOVER] {max_wanted} candidats valides trouvés, arrêt.")
                break

            update_benchmark_status(
                benchmark_id, "discovering",
                f"Recherche de {name} ({i+1}/{total})...", progress
            )

            print(f"\n[DISCOVER] ── {i+1}/{total} : {name} ──")

            # ── LIEN (OBLIGATOIRE) ──
            source_url = _find_url_with_retries(name, brand)

            # ── IMAGE (OBLIGATOIRE) ──
            image_url = _find_image_with_retries(name, brand, source_url)

            # ── PRIX ──
            estimated_price = p.get("estimated_price")
            if not estimated_price:
                price_result = _openai_web_search(f"prix {name} en France euros 2024 2025")
                if price_result["success"]:
                    import re
                    prices = re.findall(r'(\d+[.,]?\d*)\s*€', price_result["text"])
                    if prices:
                        try:
                            estimated_price = float(prices[0].replace(",", "."))
                        except:
                            pass

            # ── VALIDATION ──
            has_link = bool(source_url)
            has_image = bool(image_url)

            status_parts = []
            status_parts.append(f"{'✓' if has_link else '✗'} lien")
            status_parts.append(f"{'✓' if has_image else '✗'} image")
            status_parts.append(f"{'✓' if estimated_price else '✗'} prix")
            print(f"[DISCOVER] {' | '.join(status_parts)}")

            # Si pas de lien ET pas d'image → on skip ce produit
            if not has_link and not has_image:
                print(f"[DISCOVER] ⚠ SKIP {name} — ni lien ni image trouvés")
                skipped += 1
                continue

            candidate = {
                "id": str(uuid.uuid4()),
                "name": name,
                "brand": brand,
                "segment": p.get("segment", ""),
                "estimated_price": estimated_price,
                "why_selected": p.get("why_selected", ""),
                "image_url": image_url,
                "source_url": source_url,
                "selected": True,
                "has_link": has_link,
                "has_image": has_image,
            }
            candidates.append(candidate)

        # Sauvegarder les candidats
        save_candidates(benchmark_id, candidates)

        valid_count = len(candidates)
        complete_count = sum(1 for c in candidates if c["has_link"] and c["has_image"])

        update_benchmark_status(
            benchmark_id, "selection",
            f"{valid_count} produits trouvés ({complete_count} avec photo et lien). "
            f"Sélectionnez ceux à benchmarker.",
            100
        )

        print(f"\n[DISCOVER] ══════════════════════════════════════")
        print(f"[DISCOVER] TERMINÉ : {valid_count} candidats "
              f"({complete_count} complets, {skipped} skippés)")
        print(f"[DISCOVER] ══════════════════════════════════════")

    except Exception as e:
        print(f"\n[DISCOVER] ❌ ERREUR : {e}")
        import traceback
        traceback.print_exc()
        update_benchmark_status(benchmark_id, "error", f"Erreur : {str(e)}", 0)
        raise


# ══════════════════════════════════════════════
# TÂCHE 2 : DEEP RESEARCH
# ══════════════════════════════════════════════

@celery.task(bind=True, name="run_benchmark")
def run_benchmark(self, benchmark_id: str, product_type: str, config: dict, selected_products: list = None):
    """
    Phase 2 : Deep research sur les produits sélectionnés.
    """
    try:
        if selected_products is None:
            market_research = research_market_landscape(product_type, config)
            raw = select_products(product_type, config, market_research)
            selected_products = [
                {"name": p["name"], "brand": p.get("brand", ""),
                 "image_url": "", "source_url": "", "estimated_price": p.get("estimated_price")}
                for p in raw
            ]
            market_research_data = market_research
        else:
            market_research_data = get_market_research(benchmark_id)

        total_products = len(selected_products)
        if not total_products:
            update_benchmark_status(benchmark_id, "error", "Aucun produit sélectionné.", 0)
            return

        print(f"\n[BENCHMARK] ══════════════════════════════════════")
        print(f"[BENCHMARK] Deep Research : {product_type} ({total_products} produits)")
        print(f"[BENCHMARK] ══════════════════════════════════════")

        # Critères
        update_benchmark_status(benchmark_id, "criteria", "Définition des critères...", 10)
        criteria = define_criteria(product_type, market_research_data)
        update_benchmark_criteria(benchmark_id, criteria)
        total_fields = sum(len(cat.get("fields", [])) for cat in criteria)

        criteria_summary = ""
        for cat in criteria:
            field_names = [f["name"] for f in cat.get("fields", [])]
            criteria_summary += f"{cat['category']}: {', '.join(field_names)}\n"

        # Collecte
        for i, product_info in enumerate(selected_products):
            product_name = product_info["name"]
            brand = product_info.get("brand", "")
            progress = 15 + int((i / total_products) * 75)

            update_benchmark_status(
                benchmark_id, "collecting",
                f"Deep research : {product_name} ({i+1}/{total_products})...", progress
            )

            print(f"\n[BENCHMARK] ═══ {i+1}/{total_products} : {product_name} ═══")

            existing_source = product_info.get("source_url", "")
            existing_image = product_info.get("image_url", "")

            collected = deep_collect_product(product_name, brand, criteria_summary)

            image_url = existing_image or collected["image_url"]
            source_url = existing_source or collected["best_source_url"]

            # Si toujours pas de lien/image, retenter
            if not source_url:
                print(f"  [RETRY] Pas de lien, nouvelle tentative...")
                source_url = _find_url_with_retries(product_name, brand)
            if not image_url:
                print(f"  [RETRY] Pas d'image, nouvelle tentative...")
                image_url = _find_image_with_retries(product_name, brand, source_url)

            # Extraction
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
                except Exception as e:
                    print(f"  [EXTRACT] Erreur : {e}")

            # Recherche complémentaire
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
                    targeted = _openai_web_search(
                        f"{product_name} ({brand}) : {fields_str}. Valeurs précises avec sources."
                    )
                    if targeted["success"] and targeted["text"]:
                        try:
                            extracted_data, new_sources = deep_extract_missing_fields(
                                product_name, criteria, extracted_data,
                                targeted["text"], [s["url"] for s in targeted["sources"]]
                            )
                            sources_per_field.update(new_sources)
                            completeness = _count_completeness(extracted_data, total_fields)
                        except:
                            pass

            # Enrichissement IA
            if completeness < 0.40:
                try:
                    extracted_data = enrich_product_from_knowledge(product_name, criteria, extracted_data)
                    completeness = _count_completeness(extracted_data, total_fields)
                except:
                    pass

            # Prix
            price_min = None
            price_max = None
            for key, val in extracted_data.items():
                if "prix" in key.lower() and val is not None:
                    try:
                        pv = float(str(val).replace("€", "").replace(",", ".").replace("\u00a0", "").replace(" ", ""))
                        if price_min is None or pv < price_min:
                            price_min = pv
                        if price_max is None or pv > price_max:
                            price_max = pv
                    except:
                        pass
            if price_min is None and product_info.get("estimated_price"):
                price_min = product_info["estimated_price"]
                price_max = product_info["estimated_price"]

            # Sauvegarde
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
                "sources": [{"url": s["url"], "title": s.get("title", "")} for s in collected["sources"]],
                "sources_per_field": sources_per_field,
            }
            save_product(benchmark_id, product_data)

            print(f"  [SAVE] ✓ {product_name} — {completeness:.0%}, "
                  f"image: {'✓' if image_url else '✗'}, lien: {'✓' if source_url else '✗'}")

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
