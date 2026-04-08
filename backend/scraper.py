"""
scraper.py — Collecte web V6 + Deep Research Market Analyst.
"""
import os
import re
import json
import httpx
from bs4 import BeautifulSoup
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
REQUEST_TIMEOUT = 20.0

# ══════════════════════════════════════════════
# PROMPT D'ORCHESTRATION (DEEP RESEARCH)
# ══════════════════════════════════════════════

MARKET_ANALYST_PROMPT = """
# RÔLE ET PERSONA
Tu es un Analyste de Marché Senior et Expert en Benchmarking Stratégique. Ton objectif est de réaliser une analyse exhaustive ("Deep Research") d'une catégorie de produits spécifique, puis de sélectionner rigoureusement les produits les plus pertinents pour constituer un benchmark d'élite. 

# CONTEXTE ET RÈGLES NON NÉGOCIABLES
- QUALITÉ ABSOLUE : La qualité de l'analyse et de la sélection prime sur tout. Prends le temps d'explorer, de croiser tes sources et de réfléchir. Le temps de recherche n'est pas une contrainte.
- PERTINENCE : Une sélection de produits aléatoire ou basée uniquement sur la popularité de base est interdite. Les produits choisis doivent représenter l'état de l'art du marché (leaders, challengers innovants, meilleurs rapports qualité/prix).
- MARCHÉ : L'analyse et la disponibilité des produits doivent être centrées sur le marché Français (sauf indication contraire).

# TÂCHE ET PROCESSUS (À SUIVRE SÉQUENTIELLEMENT)

**Étape 1 : Analyse Sectorielle du Marché (Deep Research)**
Utilise tes outils de recherche web pour cartographier la catégorie de produits demandée :
- Quelles sont les tendances technologiques ou de consommation actuelles ?
- Quelles sont les marques historiques, les leaders actuels et les nouveaux disrupteurs ?
- Quels sont les "Pain Points" (points de friction) des utilisateurs et les caractéristiques les plus recherchées ?

**Étape 2 : Définition du Cadre de Référence**
Sur la base de l'Étape 1, définis 3 à 5 critères stricts qui détermineront si un produit mérite ou non d'entrer dans ce benchmark (ex: segment de prix, notation minimum des utilisateurs, technologie requise, ancienneté du produit).

**Étape 3 : Sélection Ultra-Qualitative**
Recherche et sélectionne des produits qui répondent PARFAITEMENT aux critères de l'Étape 2. Élimine impitoyablement les modèles obsolètes, les marques blanches sans SAV, ou les produits indisponibles.

# FORMAT DE SORTIE EXIGÉ
Tu dois formuler ta réponse finale sous forme d'un objet JSON structuré exactement comme suit (ce JSON sera directement lu par un script Python d'extraction de données) :

{
  "market_analysis": {
    "trends": "Résumé en 3 phrases des tendances actuelles du marché",
    "top_brands": ["Marque 1", "Marque 2", "Marque 3"],
    "selection_criteria": ["Critère 1", "Critère 2", "Critère 3"]
  },
  "selected_products": [
    {
      "brand": "Nom de la marque",
      "product_name": "Nom exact et complet du modèle",
      "justification": "Pourquoi ce produit a été sélectionné en 1 phrase courte."
    }
  ]
}
"""


# ══════════════════════════════════════════════
# VALIDATION HTTP
# ══════════════════════════════════════════════

async def _validate_url(url: str) -> bool:
    """Vérifie qu'une URL est accessible (retourne 200)."""
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as http:
            resp = await http.head(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            })
            return resp.status_code == 200
    except:
        return False


async def _validate_image_url(url: str) -> bool:
    """Vérifie qu'une URL est bien une image accessible."""
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as http:
            resp = await http.head(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            })
            if resp.status_code != 200:
                return False
            content_type = resp.headers.get("content-type", "")
            return "image" in content_type
    except:
        return False


async def _fetch_page(url: str) -> dict:
    """Télécharge une page et extrait texte + image."""
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT, follow_redirects=True) as http:
            resp = await http.get(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept-Language": "fr-FR,fr;q=0.9",
            })
            resp.raise_for_status()
            html = resp.text

        soup = BeautifulSoup(html, "html.parser")

        # Extraire l'image
        image_url = ""
        og = soup.find("meta", property="og:image")
        if og and og.get("content"):
            image_url = og["content"]
            if image_url.startswith("//"):
                image_url = "https:" + image_url
        if not image_url:
            for script in soup.find_all("script", type="application/ld+json"):
                try:
                    data = json.loads(script.string or "")
                    if isinstance(data, dict):
                        img = data.get("image")
                        if isinstance(img, str) and img:
                            image_url = img
                        elif isinstance(img, list) and img:
                            image_url = img[0] if isinstance(img[0], str) else img[0].get("url", "")
                except:
                    pass

        # Extraire le texte
        for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        text = re.sub(r"\n{3,}", "\n\n", text)

        return {"success": True, "text": text[:15000], "image_url": image_url, "url": url}

    except Exception as e:
        return {"success": False, "text": "", "image_url": "", "url": url, "error": str(e)}


# ══════════════════════════════════════════════
# OPENAI WEB SEARCH
# ══════════════════════════════════════════════

def _openai_web_search(query: str) -> dict:
    """Appel OpenAI avec web search."""
    try:
        response = client.responses.create(
            model=MODEL,
            tools=[{"type": "web_search_preview"}],
            input=query,
        )
        text = ""
        sources = []
        for item in response.output:
            if item.type == "message":
                for block in item.content:
                    if block.type == "output_text":
                        text += block.text + "\n"
                        if hasattr(block, "annotations") and block.annotations:
                            for ann in block.annotations:
                                if hasattr(ann, "url") and ann.url:
                                    sources.append({"url": ann.url, "title": getattr(ann, "title", "")})
        seen = set()
        unique = [s for s in sources if s["url"] not in seen and not seen.add(s["url"])]
        return {"success": True, "text": text, "sources": unique}
    except Exception as e:
        print(f"  [WEB] Erreur : {e}")
        return {"success": False, "text": "", "sources": [], "error": str(e)}


def _openai_json(system_prompt: str, user_prompt: str) -> dict:
    """Appel OpenAI avec web search + réponse JSON."""
    try:
        response = client.responses.create(
            model=MODEL,
            tools=[{"type": "web_search_preview"}],
            input=f"{system_prompt}\n\n{user_prompt}",
        )
        text = ""
        sources = []
        for item in response.output:
            if item.type == "message":
                for block in item.content:
                    if block.type == "output_text":
                        text += block.text + "\n"
                        if hasattr(block, "annotations") and block.annotations:
                            for ann in block.annotations:
                                if hasattr(ann, "url") and ann.url:
                                    sources.append({"url": ann.url, "title": getattr(ann, "title", "")})

        # Tenter d'extraire le JSON du texte
        json_match = re.search(r'\{[\s\S]*\}', text)
        if json_match:
            try:
                data = json.loads(json_match.group())
                return {"success": True, "data": data, "text": text, "sources": sources}
            except json.JSONDecodeError:
                pass

        return {"success": True, "data": {}, "text": text, "sources": sources}
    except Exception as e:
        return {"success": False, "data": {}, "text": "", "sources": [], "error": str(e)}


# ══════════════════════════════════════════════
# RECHERCHE DE LIEN SOURCE (OBLIGATOIRE)
# ══════════════════════════════════════════════

def find_product_url(product_name: str, brand: str) -> str:
    """Trouve et VALIDE l'URL de la fiche produit."""
    import asyncio
    print(f"  [LIEN] Recherche du lien source pour {product_name}...")

    loop = asyncio.new_event_loop()

    try:
        # Stratégie 1 : demander des URLs structurées à OpenAI
        result = _openai_json(
            "Tu dois trouver l'URL EXACTE de la fiche produit. "
            "Réponds en JSON : {\"urls\": [{\"url\": \"...\", \"site\": \"...\"}]}",
            f"Trouve les URLs des fiches produit du {product_name} ({brand}) sur : "
            f"1. amazon.fr  2. fnac.com  3. decathlon.fr  4. boulanger.com  5. site officiel {brand}. "
            f"ATTENTION : je veux la page du PRODUIT, pas une page de recherche. "
            f"L'URL ne doit PAS contenir /s?k= ou /search ou /recherche."
        )

        candidate_urls = []

        if result["success"] and result["data"].get("urls"):
            for item in result["data"]["urls"]:
                url = item.get("url", "")
                if url and "/s?" not in url and "/search" not in url:
                    candidate_urls.append(url)

        for s in result.get("sources", []):
            url = s["url"]
            if "/s?" not in url and "/search" not in url and "/recherche" not in url:
                candidate_urls.append(url)

        url_pattern = r'https?://(?:www\.)?(?:amazon\.fr|fnac\.com|decathlon\.fr|boulanger\.com|darty\.com|cdiscount\.com)[^\s<>"\')\]]*'
        text_urls = re.findall(url_pattern, result.get("text", ""))
        for url in text_urls:
            url = url.rstrip(".,;:)")
            if "/s?" not in url and "/search" not in url:
                candidate_urls.append(url)

        seen = set()
        for url in candidate_urls:
            if url in seen:
                continue
            seen.add(url)
            print(f"  [LIEN] Validation : {url[:70]}...")
            is_valid = loop.run_until_complete(_validate_url(url))
            if is_valid:
                print(f"  [LIEN] ✓ VALIDÉ : {url}")
                return url
            else:
                print(f"  [LIEN] ✗ Invalide (HTTP error)")

        print(f"  [LIEN] Stratégie 2 : recherche web classique...")
        result2 = _openai_web_search(f"{product_name} {brand} acheter site:amazon.fr OR site:fnac.com")
        for s in result2.get("sources", []):
            url = s["url"]
            if "/s?" not in url and "/search" not in url:
                is_valid = loop.run_until_complete(_validate_url(url))
                if is_valid:
                    print(f"  [LIEN] ✓ VALIDÉ (strat 2) : {url}")
                    return url

        print(f"  [LIEN] Stratégie 3 : site officiel {brand}...")
        result3 = _openai_web_search(f"{product_name} site officiel {brand}")
        for s in result3.get("sources", []):
            url = s["url"]
            is_valid = loop.run_until_complete(_validate_url(url))
            if is_valid:
                print(f"  [LIEN] ✓ VALIDÉ (officiel) : {url}")
                return url

        print(f"  [LIEN] Stratégie 4 : première source valide...")
        all_sources = result.get("sources", []) + result2.get("sources", []) + result3.get("sources", [])
        for s in all_sources:
            url = s["url"]
            if url not in seen:
                seen.add(url)
                is_valid = loop.run_until_complete(_validate_url(url))
                if is_valid:
                    print(f"  [LIEN] ✓ VALIDÉ (fallback) : {url}")
                    return url

    finally:
        loop.close()

    print(f"  [LIEN] ✗ Aucun lien validé")
    return ""


# ══════════════════════════════════════════════
# RECHERCHE D'IMAGE (OBLIGATOIRE)
# ══════════════════════════════════════════════

def find_product_image(product_name: str, brand: str, source_url: str) -> str:
    """Trouve et VALIDE l'URL de l'image du produit."""
    import asyncio
    print(f"  [IMAGE] Recherche d'image pour {product_name}...")

    loop = asyncio.new_event_loop()
    try:
        if source_url:
            blocked = ["amazon.fr", "amazon.com", "cdiscount.com"]
            if not any(d in source_url for d in blocked):
                print(f"  [IMAGE] Strat 1 : scraping {source_url[:60]}...")
                page = loop.run_until_complete(_fetch_page(source_url))
                if page["success"] and page["image_url"]:
                    is_valid = loop.run_until_complete(_validate_image_url(page["image_url"]))
                    if is_valid:
                        print(f"  [IMAGE] ✓ VALIDÉE (og:image) : {page['image_url'][:80]}")
                        return page["image_url"]

        print(f"  [IMAGE] Strat 2 : recherche OpenAI structurée...")
        result = _openai_json(
            "Trouve l'URL DIRECTE d'une image du produit (format .jpg, .png ou .webp). "
            "Réponds en JSON : {\"image_urls\": [\"url1\", \"url2\"]}",
            f"Image du produit {product_name} de {brand}. "
            f"Cherche sur amazon.fr (format https://m.media-amazon.com/images/I/...), "
            f"le site officiel {brand}, ou Google Images. "
            f"Je veux l'URL DIRECTE de l'image, pas la page web."
        )

        if result["success"]:
            image_candidates = []
            if result["data"].get("image_urls"):
                image_candidates.extend(result["data"]["image_urls"])

            img_patterns = [
                r'https://m\.media-amazon\.com/images/I/[A-Za-z0-9._+-]+\.(?:jpg|png|webp)',
                r'https?://[^\s<>"\']+\.(?:jpg|jpeg|png|webp)(?:\?[^\s<>"\']*)?',
            ]
            for pattern in img_patterns:
                matches = re.findall(pattern, result.get("text", ""))
                image_candidates.extend(matches)

            for img_url in image_candidates:
                img_url = img_url.rstrip(".,;:)")
                if len(img_url) < 20:
                    continue
                print(f"  [IMAGE] Validation : {img_url[:70]}...")
                is_valid = loop.run_until_complete(_validate_image_url(img_url))
                if is_valid:
                    print(f"  [IMAGE] ✓ VALIDÉE : {img_url[:80]}")
                    return img_url

        print(f"  [IMAGE] Strat 3 : image Amazon...")
        result3 = _openai_web_search(
            f"amazon.fr {product_name} — donne l'URL de l'image produit "
            f"(format https://m.media-amazon.com/images/I/xxxxx.jpg)"
        )
        if result3["success"]:
            amazon_imgs = re.findall(
                r'https://m\.media-amazon\.com/images/I/[A-Za-z0-9._+-]+\.(?:jpg|png)',
                result3["text"]
            )
            for img_url in amazon_imgs:
                is_valid = loop.run_until_complete(_validate_image_url(img_url))
                if is_valid:
                    print(f"  [IMAGE] ✓ VALIDÉE (Amazon) : {img_url[:80]}")
                    return img_url

        print(f"  [IMAGE] Strat 4 : scraping d'autres sources...")
        result4 = _openai_web_search(f"{product_name} {brand} photo produit")
        for s in result4.get("sources", []):
            url = s["url"]
            if any(d in url for d in ["amazon", "cdiscount", "google"]):
                continue
            page = loop.run_until_complete(_fetch_page(url))
            if page["success"] and page["image_url"]:
                is_valid = loop.run_until_complete(_validate_image_url(page["image_url"]))
                if is_valid:
                    print(f"  [IMAGE] ✓ VALIDÉE (strat 4) : {page['image_url'][:80]}")
                    return page["image_url"]

    finally:
        loop.close()

    print(f"  [IMAGE] ✗ Aucune image validée")
    return ""


# ══════════════════════════════════════════════
# COLLECTE DES DONNÉES
# ══════════════════════════════════════════════

def collect_product_data(product_name: str, brand: str, criteria_summary: str) -> dict:
    """Collecte toutes les données d'un produit."""
    import asyncio
    all_text = ""
    all_sources = []

    searches = [
        (
            f"Caractéristiques techniques complètes du {product_name} ({brand}) : "
            f"dimensions, poids, matériaux, composition, fonctionnalités, prix en France. "
            f"Donne des valeurs PRÉCISES et CHIFFRÉES.",
            "specs"
        ),
        (
            f"Avis et tests du {product_name} ({brand}) : "
            f"note moyenne sur 5, nombre d'avis, points positifs et négatifs récurrents, "
            f"conclusions des tests. Donne des chiffres précis.",
            "avis"
        ),
        (
            f"{product_name} ({brand}) : date de lancement, pays de fabrication, "
            f"positionnement marketing, segment, canaux de vente en France, innovations.",
            "infos"
        ),
    ]

    for query, label in searches:
        print(f"  [DATA] Recherche : {label}")
        result = _openai_web_search(query)
        if result["success"]:
            all_text += f"\n\n═══ {label.upper()} ═══\n{result['text']}"
            all_sources.extend(result["sources"])

    loop = asyncio.new_event_loop()
    blocked = ["amazon.fr", "amazon.com", "cdiscount.com", "google.com", "google.fr"]
    try:
        seen = set()
        for s in all_sources[:10]:
            url = s["url"]
            if url in seen or any(d in url for d in blocked):
                continue
            seen.add(url)
            page = loop.run_until_complete(_fetch_page(url))
            if page["success"] and len(page.get("text", "")) > 300:
                all_text += f"\n\n═══ SCRAPING : {url} ═══\n{page['text'][:8000]}"
    finally:
        loop.close()

    seen_urls = set()
    unique = []
    for s in all_sources:
        if s["url"] not in seen_urls:
            seen_urls.add(s["url"])
            unique.append(s)

    return {
        "text": all_text,
        "sources": unique,
        "source_urls": [s["url"] for s in unique],
    }


# ══════════════════════════════════════════════
# POINT D'ENTRÉE DU SCRAPER (UN PRODUIT)
# ══════════════════════════════════════════════

def deep_collect_product(product_name: str, brand: str, criteria_summary: str) -> dict:
    """Collecte complète pour UN produit."""
    source_url = find_product_url(product_name, brand)
    image_url = find_product_image(product_name, brand, source_url)
    data = collect_product_data(product_name, brand, criteria_summary)

    return {
        "text": data["text"],
        "sources": data["sources"],
        "source_urls": data["source_urls"],
        "image_url": image_url,
        "best_source_url": source_url,
    }


# ══════════════════════════════════════════════
# NOUVEAU POINT D'ENTRÉE GLOBAL (ANALYSE + SCRAPING)
# ══════════════════════════════════════════════

def run_market_benchmark(category_name: str, num_products: int = 5):
    """
    1. Fait l'analyse de marché (utilise le prompt)
    2. Récupère la liste JSON des meilleurs produits
    3. Lance le scraper détaillé sur chaque produit trouvé
    """
    print(f"\n🚀 DÉMARRAGE DE LA DEEP RESEARCH : {category_name}")
    print("--------------------------------------------------")
    
    # Étape 1 : On demande à OpenAI d'analyser le marché et choisir les produits
    user_prompt = f"Catégorie cible : {category_name}. Sélectionne exactement {num_products} produits."
    
    print("🧠 Phase 1 : Analyse du marché par l'IA (veuillez patienter...)")
    analyst_result = _openai_json(MARKET_ANALYST_PROMPT, user_prompt)
    
    if not analyst_result["success"] or not analyst_result["data"].get("selected_products"):
        print("❌ Erreur lors de l'analyse du marché.")
        return None

    market_data = analyst_result["data"]
    selected_products = market_data.get("selected_products", [])
    
    print(f"✅ Analyse terminée ! {len(selected_products)} produits sélectionnés.")
    criteria_summary = " | ".join(market_data.get("market_analysis", {}).get("selection_criteria", []))
    
    final_results = []
    
    # Étape 2 : On lance ton scraper sur chaque produit trouvé
    for i, prod in enumerate(selected_products, 1):
        p_name = prod.get("product_name", "")
        p_brand = prod.get("brand", "")
        
        print(f"\n📦 [{i}/{len(selected_products)}] Scraping détaillé de : {p_brand} {p_name}")
        
        scraped_data = deep_collect_product(p_name, p_brand, criteria_summary)
        
        # On assemble le résultat final pour ce produit
        final_results.append({
            "market_justification": prod.get("justification", ""),
            "product_info": prod,
            "scraped_data": scraped_data
        })
        
    print("\n🎉 TERMINÉ ! Tous les produits ont été traités.")
    return {
        "market_analysis": market_data.get("market_analysis"),
        "products": final_results
    }

# Exemple d'utilisation (décommente pour tester en local) :
# if __name__ == "__main__":
#     benchmark = run_market_benchmark("Machine à café à grain milieu de gamme", num_products=3)
#     print(json.dumps(benchmark, indent=2, ensure_ascii=False))