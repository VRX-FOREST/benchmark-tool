"""
scraper.py — Collecte web V5.

RÈGLES NON NÉGOCIABLES :
- Chaque produit DOIT avoir un lien source (URL de page produit)
- Chaque produit DOIT avoir une photo

Deux moteurs :
1. OpenAI web search (recherche + interprétation + sources)
2. Scraping direct gratuit (images et données complémentaires)
"""
import os
import re
import json
import httpx
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
REQUEST_TIMEOUT = 30.0


# ══════════════════════════════════════════════
# OPENAI WEB SEARCH
# ══════════════════════════════════════════════

def _openai_web_search(query: str) -> dict:
    """
    Appel OpenAI avec web search. Retourne texte + sources.
    """
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
                                    sources.append({
                                        "url": ann.url,
                                        "title": getattr(ann, "title", ""),
                                    })

        # Dédupliquer
        seen = set()
        unique = []
        for s in sources:
            if s["url"] not in seen:
                seen.add(s["url"])
                unique.append(s)

        return {"success": True, "text": text, "sources": unique}

    except Exception as e:
        print(f"  [WEB] Erreur : {e}")
        return {"success": False, "text": "", "sources": [], "error": str(e)}


# ══════════════════════════════════════════════
# RECHERCHE DE LIEN SOURCE (OBLIGATOIRE)
# ══════════════════════════════════════════════

def find_product_url(product_name: str, brand: str) -> str:
    """
    Trouve l'URL de la page produit. Essaie plusieurs stratégies.
    Ne retourne "" que si TOUTES les stratégies échouent.
    """
    print(f"  [LIEN] Recherche du lien source pour {product_name}...")

    # Stratégie 1 : demander directement l'URL à OpenAI
    result = _openai_web_search(
        f"Donne-moi l'URL exacte de la page produit du {product_name} de {brand} "
        f"sur un site marchand français (amazon.fr, fnac.com, decathlon.fr, "
        f"boulanger.com, darty.com, cdiscount.com) ou sur le site officiel {brand}. "
        f"Je veux l'URL DIRECTE de la fiche produit, PAS une page de recherche."
    )

    if result["success"]:
        # Chercher dans les sources
        priority_domains = [
            "amazon.fr", "fnac.com", "decathlon.fr", "boulanger.com",
            "darty.com", "cdiscount.com", "materiel.net",
        ]
        # Priorité aux sites marchands connus
        for s in result["sources"]:
            url = s["url"]
            if any(d in url for d in priority_domains):
                # Vérifier que ce n'est pas une page de recherche
                if "/s?" not in url and "/search" not in url and "/recherche" not in url:
                    print(f"  [LIEN] ✓ Trouvé (marchand) : {url}")
                    return url

        # Sinon, chercher les URLs dans le texte de la réponse
        url_pattern = r'https?://[^\s<>"\')\]]+(?:/[^\s<>"\')\]]+)*'
        text_urls = re.findall(url_pattern, result["text"])
        for url in text_urls:
            # Nettoyer les URLs
            url = url.rstrip(".,;:)")
            if any(d in url for d in priority_domains):
                if "/s?" not in url and "/search" not in url:
                    print(f"  [LIEN] ✓ Trouvé (dans texte) : {url}")
                    return url

        # Prendre la première source disponible
        for s in result["sources"]:
            url = s["url"]
            if "/s?" not in url and "/search" not in url:
                print(f"  [LIEN] ✓ Trouvé (source) : {url}")
                return url

    # Stratégie 2 : recherche plus spécifique
    print(f"  [LIEN] Stratégie 2 : recherche site marchand spécifique...")
    result2 = _openai_web_search(
        f"site:amazon.fr {product_name} OU site:fnac.com {product_name} — "
        f"donne-moi le lien direct vers la fiche produit"
    )
    if result2["success"] and result2["sources"]:
        for s in result2["sources"]:
            if "/s?" not in s["url"] and "/search" not in s["url"]:
                print(f"  [LIEN] ✓ Trouvé (strat 2) : {s['url']}")
                return s["url"]

    # Stratégie 3 : site officiel de la marque
    print(f"  [LIEN] Stratégie 3 : site officiel {brand}...")
    result3 = _openai_web_search(
        f"Trouve la page produit officielle du {product_name} sur le site de {brand}. "
        f"Donne l'URL exacte."
    )
    if result3["success"] and result3["sources"]:
        for s in result3["sources"]:
            print(f"  [LIEN] ✓ Trouvé (officiel) : {s['url']}")
            return s["url"]

    print(f"  [LIEN] ✗ Aucun lien trouvé après 3 stratégies")
    return ""


# ══════════════════════════════════════════════
# RECHERCHE D'IMAGE (OBLIGATOIRE)
# ══════════════════════════════════════════════

def _extract_image_from_html(html: str, url: str) -> str:
    """Extrait la meilleure image d'une page HTML."""
    soup = BeautifulSoup(html, "html.parser")

    # OpenGraph
    og = soup.find("meta", property="og:image")
    if og and og.get("content"):
        img_url = og["content"]
        if img_url.startswith("//"):
            img_url = "https:" + img_url
        return img_url

    # Twitter card
    tw = soup.find("meta", attrs={"name": "twitter:image"})
    if tw and tw.get("content"):
        return tw["content"]

    # JSON-LD
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            if isinstance(data, dict):
                img = data.get("image")
                if isinstance(img, str) and img:
                    return img
                if isinstance(img, list) and img:
                    return img[0] if isinstance(img[0], str) else img[0].get("url", "")
                if isinstance(img, dict):
                    return img.get("url", "")
        except:
            pass

    return ""


async def _async_fetch(url: str) -> dict:
    """Fetch HTTP simple."""
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT, follow_redirects=True) as http:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept-Language": "fr-FR,fr;q=0.9",
            }
            resp = await http.get(url, headers=headers)
            resp.raise_for_status()
            return {"success": True, "html": resp.text, "url": url}
    except Exception as e:
        return {"success": False, "html": "", "url": url, "error": str(e)}


def find_product_image(product_name: str, brand: str, source_url: str) -> str:
    """
    Trouve l'image du produit. Essaie plusieurs stratégies.
    Ne retourne "" que si TOUT échoue.
    """
    import asyncio
    print(f"  [IMAGE] Recherche d'image pour {product_name}...")

    # Stratégie 1 : scraper la page source pour récupérer l'og:image
    if source_url:
        # Ignorer Amazon (bloqué) mais tenter les autres
        blocked = ["amazon.fr", "amazon.com", "cdiscount.com"]
        if not any(d in source_url for d in blocked):
            print(f"  [IMAGE] Stratégie 1 : scraping direct de {source_url[:60]}...")
            loop = asyncio.new_event_loop()
            try:
                page = loop.run_until_complete(_async_fetch(source_url))
            finally:
                loop.close()

            if page["success"]:
                img = _extract_image_from_html(page["html"], source_url)
                if img:
                    print(f"  [IMAGE] ✓ Trouvée (og:image) : {img[:80]}...")
                    return img

    # Stratégie 2 : demander à OpenAI de trouver une URL d'image
    print(f"  [IMAGE] Stratégie 2 : recherche OpenAI...")
    result = _openai_web_search(
        f"Trouve une image du produit {product_name} de {brand}. "
        f"Je veux l'URL DIRECTE d'une image .jpg ou .png du produit "
        f"(pas le logo de la marque, l'image du PRODUIT lui-même). "
        f"Cherche sur Google Images, amazon.fr, ou le site officiel {brand}."
    )

    if result["success"]:
        # Chercher des URLs d'images dans le texte
        img_patterns = [
            r'https?://[^\s<>"\']+\.(?:jpg|jpeg|png|webp)(?:\?[^\s<>"\']*)?',
            r'https?://m\.media-amazon\.com/images/[^\s<>"\']+',
            r'https?://[^\s<>"\']*(?:product|media|image|photo)[^\s<>"\']*\.(?:jpg|jpeg|png|webp)',
        ]
        for pattern in img_patterns:
            matches = re.findall(pattern, result["text"], re.IGNORECASE)
            if matches:
                img_url = matches[0].rstrip(".,;:)")
                print(f"  [IMAGE] ✓ Trouvée (OpenAI texte) : {img_url[:80]}...")
                return img_url

        # Chercher dans les sources une URL qui est une image
        for s in result["sources"]:
            url = s["url"]
            if any(ext in url.lower() for ext in [".jpg", ".png", ".webp", "media-amazon"]):
                print(f"  [IMAGE] ✓ Trouvée (source) : {url[:80]}...")
                return url

    # Stratégie 3 : scraper le site officiel de la marque
    print(f"  [IMAGE] Stratégie 3 : site officiel {brand}...")
    result3 = _openai_web_search(
        f"Trouve la page du produit {product_name} sur le site officiel {brand} "
        f"et donne-moi l'URL de l'image principale du produit."
    )
    if result3["success"]:
        for pattern in img_patterns:
            matches = re.findall(pattern, result3["text"], re.IGNORECASE)
            if matches:
                img_url = matches[0].rstrip(".,;:)")
                print(f"  [IMAGE] ✓ Trouvée (strat 3) : {img_url[:80]}...")
                return img_url

    # Stratégie 4 : construire une URL Amazon probable
    print(f"  [IMAGE] Stratégie 4 : recherche image Amazon...")
    result4 = _openai_web_search(
        f"amazon.fr {product_name} — "
        f"copie l'URL de l'image principale du produit (format https://m.media-amazon.com/images/...)"
    )
    if result4["success"]:
        amazon_img = re.findall(r'https://m\.media-amazon\.com/images/I/[^\s<>"\']+', result4["text"])
        if amazon_img:
            img_url = amazon_img[0].rstrip(".,;:)")
            print(f"  [IMAGE] ✓ Trouvée (Amazon) : {img_url[:80]}...")
            return img_url

    print(f"  [IMAGE] ✗ Aucune image trouvée après 4 stratégies")
    return ""


# ══════════════════════════════════════════════
# COLLECTE DES DONNÉES PRODUIT
# ══════════════════════════════════════════════

def collect_product_data(product_name: str, brand: str, criteria_summary: str) -> dict:
    """
    Collecte COMPLÈTE : données techniques + avis + prix.
    Retourne le texte brut combiné et la liste des sources.
    """
    all_text = ""
    all_sources = []

    searches = [
        (
            f"Caractéristiques techniques complètes du {product_name} ({brand}) : "
            f"dimensions, poids, matériaux, composition, fonctionnalités, "
            f"spécifications détaillées. Prix actuel en France. "
            f"Cherche sur amazon.fr, fnac.com, decathlon.fr, le site officiel {brand}, "
            f"et les sites de test français.",
            "specs"
        ),
        (
            f"Avis et tests du {product_name} ({brand}) : "
            f"note moyenne des utilisateurs (sur 5), nombre total d'avis, "
            f"points positifs récurrents dans les avis, points négatifs récurrents, "
            f"conclusions des tests professionnels. "
            f"Cherche sur amazon.fr, quechoisir.org, lesnumeriques.com.",
            "avis"
        ),
        (
            f"Informations complémentaires sur le {product_name} ({brand}) : "
            f"date de lancement, pays de fabrication, procédé de fabrication, "
            f"positionnement marketing, segment de marché, canaux de distribution en France, "
            f"innovations techniques ou brevets.",
            "infos"
        ),
    ]

    for query, label in searches:
        print(f"  [DATA] Recherche : {label}")
        result = _openai_web_search(query)
        if result["success"]:
            all_text += f"\n\n═══ {label.upper()} ═══\n{result['text']}"
            all_sources.extend(result["sources"])
            print(f"  [DATA] → {len(result['sources'])} sources")

    # Dédupliquer
    seen = set()
    unique_sources = []
    for s in all_sources:
        if s["url"] not in seen:
            seen.add(s["url"])
            unique_sources.append(s)

    # Scraping direct des sources accessibles (complément gratuit)
    print(f"  [DATA] Scraping direct des sources accessibles...")
    import asyncio
    blocked = ["amazon.fr", "amazon.com", "cdiscount.com", "google.com"]

    loop = asyncio.new_event_loop()
    try:
        for s in unique_sources[:8]:  # Max 8 URLs
            url = s["url"]
            if any(d in url for d in blocked):
                continue
            page = loop.run_until_complete(_async_fetch(url))
            if page["success"]:
                soup = BeautifulSoup(page["html"], "html.parser")
                for tag in soup(["script", "style", "nav", "footer", "header"]):
                    tag.decompose()
                page_text = soup.get_text(separator="\n", strip=True)
                if len(page_text) > 300:
                    all_text += f"\n\n═══ SCRAPING DIRECT : {url} ═══\n{page_text[:8000]}"
                    print(f"  [DATA] ✓ Scraping : {url[:60]}...")
    finally:
        loop.close()

    return {
        "text": all_text,
        "sources": unique_sources,
        "source_urls": [s["url"] for s in unique_sources],
    }


# ══════════════════════════════════════════════
# POINT D'ENTRÉE PRINCIPAL
# ══════════════════════════════════════════════

def deep_collect_product(product_name: str, brand: str, criteria_summary: str) -> dict:
    """
    Collecte complète d'un produit.
    GARANTIT un lien source et une image (ou fait tout son possible).
    """
    # 1. Trouver le lien source (OBLIGATOIRE)
    source_url = find_product_url(product_name, brand)

    # 2. Trouver l'image (OBLIGATOIRE)
    image_url = find_product_image(product_name, brand, source_url)

    # 3. Collecter les données
    data = collect_product_data(product_name, brand, criteria_summary)

    return {
        "text": data["text"],
        "sources": data["sources"],
        "source_urls": data["source_urls"],
        "image_url": image_url,
        "best_source_url": source_url,
    }
