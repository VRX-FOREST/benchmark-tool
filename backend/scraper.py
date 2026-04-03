"""
scraper.py — Collecte de données web.
Utilise httpx + BeautifulSoup pour le scraping léger,
et ScraperAPI pour contourner les protections anti-bot.
"""
import os
import re
import httpx
from bs4 import BeautifulSoup
from urllib.parse import urlencode

SCRAPER_API_KEY = os.getenv("SCRAPER_API_KEY", "")
SCRAPER_API_URL = "https://api.scraperapi.com"
REQUEST_TIMEOUT = 30.0


async def fetch_page(url: str, use_scraper_api: bool = True) -> dict:
    """
    Récupère le contenu d'une page web.
    
    Args:
        url: URL de la page à scraper
        use_scraper_api: Si True, utilise ScraperAPI pour contourner les anti-bots
    
    Returns:
        {"success": bool, "html": str, "text": str, "title": str}
    """
    try:
        if use_scraper_api and SCRAPER_API_KEY:
            # Passer par ScraperAPI
            params = {
                "api_key": SCRAPER_API_KEY,
                "url": url,
                "render": "true",  # Active le rendu JavaScript
            }
            fetch_url = f"{SCRAPER_API_URL}?{urlencode(params)}"
        else:
            fetch_url = url

        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT, follow_redirects=True) as client:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
            }
            response = await client.get(fetch_url, headers=headers)
            response.raise_for_status()
            html = response.text

        soup = BeautifulSoup(html, "html.parser")

        # Supprimer les scripts et styles pour un texte propre
        for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
            tag.decompose()

        # Extraire le texte nettoyé
        text = soup.get_text(separator="\n", strip=True)
        # Supprimer les lignes vides multiples
        text = re.sub(r"\n{3,}", "\n\n", text)

        # Extraire le titre
        title = ""
        title_tag = soup.find("title")
        if title_tag:
            title = title_tag.get_text(strip=True)

        return {
            "success": True,
            "html": html,
            "text": text[:15000],  # Limiter la taille pour l'API OpenAI
            "title": title,
            "url": url,
        }

    except Exception as e:
        return {
            "success": False,
            "html": "",
            "text": "",
            "title": "",
            "url": url,
            "error": str(e),
        }


async def extract_product_image(html: str, url: str) -> str:
    """
    Extrait l'URL de l'image principale du produit depuis le HTML.
    Cherche en priorité les balises OpenGraph, puis les grandes images.
    """
    soup = BeautifulSoup(html, "html.parser")

    # 1. OpenGraph image (og:image) — la plus fiable
    og_image = soup.find("meta", property="og:image")
    if og_image and og_image.get("content"):
        return og_image["content"]

    # 2. Twitter card image
    twitter_image = soup.find("meta", attrs={"name": "twitter:image"})
    if twitter_image and twitter_image.get("content"):
        return twitter_image["content"]

    # 3. Première grande image dans le contenu
    for img in soup.find_all("img"):
        src = img.get("src", "") or img.get("data-src", "")
        if not src:
            continue
        # Ignorer les petites icônes et logos
        width = img.get("width", "0")
        height = img.get("height", "0")
        try:
            if int(width) >= 200 or int(height) >= 200:
                if src.startswith("//"):
                    src = "https:" + src
                elif src.startswith("/"):
                    from urllib.parse import urlparse
                    parsed = urlparse(url)
                    src = f"{parsed.scheme}://{parsed.netloc}{src}"
                return src
        except (ValueError, TypeError):
            continue

    # 4. Fallback : première image avec un src contenant "product" ou "image"
    for img in soup.find_all("img"):
        src = img.get("src", "") or img.get("data-src", "")
        if src and any(kw in src.lower() for kw in ["product", "image", "photo", "media"]):
            if src.startswith("//"):
                src = "https:" + src
            return src

    return ""


async def scrape_product(url: str) -> dict:
    """
    Scrape complet d'une page produit.
    Retourne le texte extrait, l'image, et le titre.
    """
    page = await fetch_page(url)
    if not page["success"]:
        return page

    image_url = await extract_product_image(page["html"], url)
    page["image_url"] = image_url
    return page


async def search_web(query: str, num_results: int = 5) -> list[dict]:
    """
    Recherche web via ScraperAPI Google Search.
    Retourne une liste de résultats avec titre, URL et snippet.
    """
    if not SCRAPER_API_KEY:
        return []

    try:
        params = {
            "api_key": SCRAPER_API_KEY,
            "query": query,
            "country": "fr",
        }
        search_url = f"https://api.scraperapi.com/structured/google/search?{urlencode(params)}"

        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            response = await client.get(search_url)
            response.raise_for_status()
            data = response.json()

        results = []
        for item in data.get("organic_results", [])[:num_results]:
            results.append({
                "title": item.get("title", ""),
                "url": item.get("link", ""),
                "snippet": item.get("snippet", ""),
            })
        return results

    except Exception as e:
        return []
