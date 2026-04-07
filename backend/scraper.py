"""
scraper.py — Collecte web V4.

Deux moteurs de collecte :
1. PRIMAIRE : OpenAI web search (GPT-4o cherche lui-même sur le web et source ses réponses)
2. SECONDAIRE : Scraping direct gratuit (httpx sans proxy — pour les sites non protégés)

Avantages :
- Zéro service tiers payant
- Le LLM cherche, interprète et source les données en une seule passe
- Le scraping direct complète avec les pages accessibles (sites de test, fabricants)
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
# MOTEUR 1 : OPENAI WEB SEARCH (source principale)
# ══════════════════════════════════════════════

def openai_web_research(product_name: str, research_query: str) -> dict:
    """
    Utilise GPT-4o avec l'outil web search pour chercher des informations
    sur un produit. Le LLM cherche lui-même sur le web et cite ses sources.
    
    Retourne : {"text": str, "sources": [{"url": str, "title": str}]}
    """
    try:
        response = client.responses.create(
            model=MODEL,
            tools=[{"type": "web_search_preview"}],
            input=research_query,
        )

        # Extraire le texte et les sources
        text = ""
        sources = []

        for item in response.output:
            if item.type == "message":
                for block in item.content:
                    if block.type == "output_text":
                        text += block.text + "\n"
                        # Extraire les annotations (citations avec URLs)
                        if hasattr(block, "annotations") and block.annotations:
                            for ann in block.annotations:
                                if hasattr(ann, "url") and ann.url:
                                    sources.append({
                                        "url": ann.url,
                                        "title": getattr(ann, "title", ""),
                                    })

        # Dédupliquer les sources
        seen_urls = set()
        unique_sources = []
        for s in sources:
            if s["url"] not in seen_urls:
                seen_urls.add(s["url"])
                unique_sources.append(s)

        return {
            "success": True,
            "text": text,
            "sources": unique_sources,
        }

    except Exception as e:
        print(f"  [WEB SEARCH] Erreur : {e}")
        return {"success": False, "text": "", "sources": [], "error": str(e)}


def research_product_complete(product_name: str, brand: str, criteria_summary: str) -> dict:
    """
    Recherche COMPLÈTE d'un produit via OpenAI web search.
    Fait plusieurs recherches ciblées pour couvrir tous les aspects.
    """
    all_text = ""
    all_sources = []

    searches = [
        {
            "query": f"Recherche les caractéristiques techniques complètes, le prix actuel en France, "
                     f"et les spécifications détaillées du produit : {product_name}. "
                     f"Cherche sur amazon.fr, fnac.com, le site officiel {brand}, "
                     f"et les sites de test français. "
                     f"Donne-moi TOUTES les données techniques : dimensions, poids, matériaux, "
                     f"fonctionnalités, avec les URLs sources.",
            "label": "specs_et_prix"
        },
        {
            "query": f"Recherche les avis et tests du {product_name} en France. "
                     f"Je veux : la note moyenne des utilisateurs, le nombre d'avis, "
                     f"les points positifs et négatifs récurrents dans les avis, "
                     f"et les conclusions des tests professionnels. "
                     f"Cherche sur amazon.fr, lesnumeriques.com, quechoisir.org, "
                     f"et les forums spécialisés. Donne les URLs sources.",
            "label": "avis_et_tests"
        },
        {
            "query": f"Trouve l'URL exacte de la page produit du {product_name} sur amazon.fr "
                     f"ou sur le site officiel {brand}. "
                     f"Donne-moi aussi l'URL d'une image haute qualité du produit. "
                     f"Je veux le lien DIRECT vers la fiche produit, pas une page de recherche.",
            "label": "urls_et_images"
        },
    ]

    for search in searches:
        print(f"  [WEB SEARCH] Recherche : {search['label']}")
        result = openai_web_research(product_name, search["query"])
        if result["success"]:
            all_text += f"\n\n═══ {search['label']} ═══\n{result['text']}"
            all_sources.extend(result["sources"])
            print(f"  [WEB SEARCH] → {len(result['sources'])} sources trouvées")
        else:
            print(f"  [WEB SEARCH] → Échec : {result.get('error', '?')}")

    # Dédupliquer les sources
    seen = set()
    unique_sources = []
    for s in all_sources:
        if s["url"] not in seen:
            seen.add(s["url"])
            unique_sources.append(s)

    return {
        "text": all_text,
        "sources": unique_sources,
    }


def find_product_image_via_search(product_name: str) -> str:
    """
    Recherche spécifique pour trouver l'image du produit.
    """
    try:
        result = openai_web_research(
            product_name,
            f"Trouve l'image officielle du produit {product_name}. "
            f"Donne-moi l'URL directe de l'image (format .jpg ou .png) "
            f"depuis amazon.fr, le site officiel, ou un site marchand français."
        )
        if result["success"]:
            # Chercher les URLs d'images dans le texte
            img_pattern = r'https?://[^\s<>"\']+\.(?:jpg|jpeg|png|webp)[^\s<>"\']*'
            matches = re.findall(img_pattern, result["text"], re.IGNORECASE)
            if matches:
                return matches[0]
            # Sinon chercher dans les sources
            for s in result["sources"]:
                if any(ext in s["url"].lower() for ext in [".jpg", ".png", ".webp"]):
                    return s["url"]
    except Exception as e:
        print(f"  [IMAGE] Erreur recherche image : {e}")

    return ""


# ══════════════════════════════════════════════
# MOTEUR 2 : SCRAPING DIRECT GRATUIT (source secondaire)
# ══════════════════════════════════════════════

def _clean_text(html: str) -> str:
    """Extrait le texte lisible d'une page HTML."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "noscript", "iframe", "svg"]):
        tag.decompose()
    text = soup.get_text(separator="\n", strip=True)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def _extract_og_image(html: str) -> str:
    """Extrait l'image OpenGraph d'une page HTML."""
    soup = BeautifulSoup(html, "html.parser")

    og = soup.find("meta", property="og:image")
    if og and og.get("content"):
        return og["content"]

    tw = soup.find("meta", attrs={"name": "twitter:image"})
    if tw and tw.get("content"):
        return tw["content"]

    # JSON-LD
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            if isinstance(data, dict):
                img = data.get("image")
                if isinstance(img, str):
                    return img
                if isinstance(img, list) and img:
                    return img[0] if isinstance(img[0], str) else img[0].get("url", "")
                if isinstance(img, dict):
                    return img.get("url", "")
        except (json.JSONDecodeError, TypeError):
            pass

    return ""


async def direct_scrape(url: str) -> dict:
    """
    Scraping direct SANS proxy. Gratuit mais bloqué sur certains sites protégés.
    Fonctionne bien sur : sites fabricants, blogs, sites de test, comparateurs.
    """
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT, follow_redirects=True) as http:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                              "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }
            response = await http.get(url, headers=headers)
            response.raise_for_status()
            html = response.text

        text = _clean_text(html)
        image_url = _extract_og_image(html)

        title = ""
        soup = BeautifulSoup(html, "html.parser")
        title_tag = soup.find("title")
        if title_tag:
            title = title_tag.get_text(strip=True)

        return {
            "success": True,
            "url": url,
            "text": text[:15000],
            "title": title,
            "image_url": image_url,
            "html": html,
        }

    except Exception as e:
        return {
            "success": False,
            "url": url,
            "text": "",
            "title": "",
            "image_url": "",
            "error": str(e),
        }


async def try_scrape_urls(urls: list[str]) -> list[dict]:
    """
    Tente de scraper une liste d'URLs en direct (gratuit).
    Retourne les pages qui ont réussi.
    """
    results = []
    for url in urls:
        # Ignorer les URLs qui seront certainement bloquées
        blocked_domains = ["amazon.fr", "amazon.com", "cdiscount.com"]
        if any(d in url for d in blocked_domains):
            continue

        page = await direct_scrape(url)
        if page["success"] and len(page.get("text", "")) > 200:
            results.append(page)
            print(f"  [SCRAPE] ✓ {url[:80]}...")
        else:
            print(f"  [SCRAPE] ✗ {url[:80]}... ({page.get('error', 'contenu trop court')})")

    return results


# ══════════════════════════════════════════════
# COLLECTE COMBINÉE
# ══════════════════════════════════════════════

def deep_collect_product(
    product_name: str,
    brand: str,
    criteria_summary: str,
) -> dict:
    """
    Collecte complète d'un produit en combinant :
    1. OpenAI web search (source principale — fiable et sourcée)
    2. Scraping direct des URLs trouvées (source complémentaire — gratuit)
    
    Retourne toutes les données brutes + sources + image.
    """
    import asyncio

    print(f"  [COLLECT] ── Moteur 1 : OpenAI Web Search ──")

    # Étape 1 : Recherche web via OpenAI
    research = research_product_complete(product_name, brand, criteria_summary)

    all_text = research["text"]
    all_sources = research["sources"]
    image_url = ""
    best_source_url = ""

    # Identifier la meilleure source (page produit sur site marchand)
    priority_domains = [
        "amazon.fr", "fnac.com", "decathlon.fr", "boulanger.com",
        "darty.com", "cdiscount.com",
    ]
    for s in all_sources:
        if any(d in s["url"] for d in priority_domains):
            best_source_url = s["url"]
            break
    if not best_source_url and all_sources:
        best_source_url = all_sources[0]["url"]

    # Étape 2 : Scraping direct des URLs trouvées (gratuit, pour compléter)
    print(f"  [COLLECT] ── Moteur 2 : Scraping direct (gratuit) ──")
    scrapeable_urls = [s["url"] for s in all_sources]

    loop = asyncio.new_event_loop()
    try:
        scraped_pages = loop.run_until_complete(try_scrape_urls(scrapeable_urls))
    finally:
        loop.close()

    for page in scraped_pages:
        all_text += f"\n\n═══ Scraping direct : {page['url']} ═══\n{page['text']}"
        if not image_url and page.get("image_url"):
            image_url = page["image_url"]
            print(f"  [COLLECT] Image trouvée via scraping : {image_url[:80]}...")

    # Étape 3 : Si pas d'image, recherche spécifique
    if not image_url:
        print(f"  [COLLECT] ── Recherche d'image spécifique ──")
        image_url = find_product_image_via_search(product_name)
        if image_url:
            print(f"  [COLLECT] Image trouvée via recherche : {image_url[:80]}...")
        else:
            print(f"  [COLLECT] ✗ Aucune image trouvée")

    source_urls = [s["url"] for s in all_sources]
    # Ajouter les URLs scrapées directement
    for page in scraped_pages:
        if page["url"] not in source_urls:
            source_urls.append(page["url"])
            all_sources.append({"url": page["url"], "title": page.get("title", "")})

    print(f"  [COLLECT] Total : {len(all_sources)} sources, "
          f"image: {'✓' if image_url else '✗'}, "
          f"texte: {len(all_text)} caractères")

    return {
        "text": all_text,
        "sources": all_sources,
        "source_urls": source_urls,
        "image_url": image_url,
        "best_source_url": best_source_url,
    }
