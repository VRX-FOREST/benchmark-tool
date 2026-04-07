"""
scraper.py — Collecte web approfondie.

Stratégie de scraping professionnel :
1. Recherche Google → obtenir des URLs candidates
2. Pour chaque URL, vérifier que c'est bien une PAGE PRODUIT (pas une page de recherche)
3. Scraper la page produit confirmée
4. Extraire l'image produit de manière fiable
5. Collecter depuis PLUSIEURS sources pour croiser les données

Le temps de collecte n'est PAS un critère — seule la qualité compte.
"""
import os
import re
import httpx
from bs4 import BeautifulSoup
from urllib.parse import urlencode, urlparse, urljoin

SCRAPER_API_KEY = os.getenv("SCRAPER_API_KEY", "")
SCRAPER_API_URL = "https://api.scraperapi.com"
REQUEST_TIMEOUT = 60.0  # Timeout long — on ne presse pas


# ─── UTILITAIRES ───

def _clean_text(html: str) -> str:
    """Extrait le texte lisible d'une page HTML."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "noscript", "iframe", "svg"]):
        tag.decompose()
    text = soup.get_text(separator="\n", strip=True)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def _extract_all_images(html: str, base_url: str) -> list[dict]:
    """
    Extrait TOUTES les images candidates d'une page, classées par pertinence.
    Retourne une liste triée : les images produit probables en premier.
    """
    soup = BeautifulSoup(html, "html.parser")
    images = []

    # 1. OpenGraph image — la plus fiable
    og = soup.find("meta", property="og:image")
    if og and og.get("content"):
        images.append({"url": og["content"], "source": "og:image", "priority": 1})

    # 2. Twitter card
    tw = soup.find("meta", attrs={"name": "twitter:image"})
    if tw and tw.get("content"):
        images.append({"url": tw["content"], "source": "twitter:image", "priority": 2})

    # 3. JSON-LD product image (schema.org)
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            import json
            data = json.loads(script.string or "")
            if isinstance(data, dict):
                img = data.get("image")
                if img:
                    if isinstance(img, list):
                        img = img[0]
                    if isinstance(img, str):
                        images.append({"url": img, "source": "json-ld", "priority": 1})
                    elif isinstance(img, dict):
                        images.append({"url": img.get("url", ""), "source": "json-ld", "priority": 1})
        except (json.JSONDecodeError, TypeError):
            pass

    # 4. Images dans le contenu principal (heuristique : grandes images)
    for img in soup.find_all("img"):
        src = img.get("src", "") or img.get("data-src", "") or img.get("data-lazy-src", "")
        if not src or len(src) < 10:
            continue

        # Résoudre les URLs relatives
        if src.startswith("//"):
            src = "https:" + src
        elif src.startswith("/"):
            parsed = urlparse(base_url)
            src = f"{parsed.scheme}://{parsed.netloc}{src}"

        # Filtrer les petites icônes
        width = img.get("width", "0")
        height = img.get("height", "0")
        alt = (img.get("alt", "") or "").lower()

        # Indicateurs de pertinence
        priority = 5
        if any(kw in src.lower() for kw in ["product", "produit", "media/catalog"]):
            priority = 3
        if any(kw in alt for kw in ["product", "produit", "photo"]):
            priority = 3
        try:
            if int(width) >= 300 or int(height) >= 300:
                priority = min(priority, 3)
        except (ValueError, TypeError):
            pass

        # Exclure les images clairement non-produit
        if any(kw in src.lower() for kw in ["logo", "icon", "sprite", "pixel", "tracking", "banner", "ad-"]):
            continue

        images.append({"url": src, "source": "img-tag", "priority": priority})

    # Trier par priorité
    images.sort(key=lambda x: x["priority"])

    # Dédupliquer
    seen = set()
    unique = []
    for img in images:
        if img["url"] not in seen and img["url"]:
            seen.add(img["url"])
            unique.append(img)

    return unique


def _is_product_page(url: str, html: str, product_name: str) -> bool:
    """
    Vérifie qu'une URL est bien une page produit et pas une page de recherche/listing.
    """
    url_lower = url.lower()

    # Pages de recherche évidentes
    search_indicators = ["/s?k=", "/search?", "/recherche?", "query=", "/gp/search", "/s/ref="]
    if any(ind in url_lower for ind in search_indicators):
        return False

    # Vérifier que le titre ou le contenu mentionne le produit
    soup = BeautifulSoup(html, "html.parser")
    title = (soup.find("title") or soup.new_tag("title"))
    title_text = title.get_text(strip=True).lower() if title else ""

    # Le nom de la marque ou du modèle doit apparaître dans le titre
    product_words = product_name.lower().split()
    # Au moins 2 mots du nom du produit dans le titre
    matches = sum(1 for word in product_words if word in title_text and len(word) > 2)
    if matches >= 2:
        return True

    # Indicateurs de page produit dans l'URL
    product_url_indicators = ["/dp/", "/product/", "/produit/", "/p/", "/fiche-technique/"]
    if any(ind in url_lower for ind in product_url_indicators):
        return True

    return False


# ─── SCRAPING PRINCIPAL ───


async def fetch_page(url: str, use_scraper_api: bool = True) -> dict:
    """
    Récupère le contenu brut d'une page web.
    """
    try:
        if use_scraper_api and SCRAPER_API_KEY:
            params = {
                "api_key": SCRAPER_API_KEY,
                "url": url,
                "render": "true",
                "country_code": "fr",
            }
            fetch_url = f"{SCRAPER_API_URL}?{urlencode(params)}"
        else:
            fetch_url = url

        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT, follow_redirects=True) as client:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                              "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }
            response = await client.get(fetch_url, headers=headers)
            response.raise_for_status()
            html = response.text

        text = _clean_text(html)

        title = ""
        soup = BeautifulSoup(html, "html.parser")
        title_tag = soup.find("title")
        if title_tag:
            title = title_tag.get_text(strip=True)

        return {
            "success": True,
            "html": html,
            "text": text[:20000],  # Plus de texte pour la deep research
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


async def scrape_product_page(url: str, product_name: str) -> dict:
    """
    Scrape une page produit confirmée.
    Retourne le texte, les images candidates, et les métadonnées.
    """
    page = await fetch_page(url)
    if not page["success"]:
        return {**page, "is_product_page": False, "images": [], "image_url": ""}

    is_product = _is_product_page(url, page["html"], product_name)
    images = _extract_all_images(page["html"], url)
    best_image = images[0]["url"] if images else ""

    return {
        **page,
        "is_product_page": is_product,
        "images": images,
        "image_url": best_image,
    }


async def search_web(query: str, num_results: int = 10) -> list[dict]:
    """
    Recherche Google via ScraperAPI.
    Retourne plus de résultats pour la deep research.
    """
    if not SCRAPER_API_KEY:
        return []

    try:
        params = {
            "api_key": SCRAPER_API_KEY,
            "query": query,
            "country": "fr",
            "num": str(num_results),
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
        print(f"  [SCRAPER] Erreur recherche '{query}': {e}")
        return []


async def search_product_page(product_name: str, site_filter: str = "") -> dict | None:
    """
    Cherche LA page produit exacte pour un produit donné.
    Filtre optionnel par site (ex: "amazon.fr").
    
    Retourne la première page CONFIRMÉE comme page produit, ou None.
    """
    query = f"{product_name}"
    if site_filter:
        query = f"site:{site_filter} {product_name}"

    results = await search_web(query, num_results=8)

    for result in results:
        url = result.get("url", "")
        if not url:
            continue

        # Pré-filtrer les URLs évidemment mauvaises
        if any(bad in url.lower() for bad in ["/s?k=", "/search?", "/recherche?"]):
            continue

        page = await scrape_product_page(url, product_name)
        if page["success"] and page["is_product_page"]:
            print(f"  [SCRAPER] ✓ Page produit trouvée : {url}")
            return page

        # Si pas confirmée comme page produit mais contenu riche, garder quand même
        if page["success"] and len(page.get("text", "")) > 500:
            print(f"  [SCRAPER] ~ Page candidate (non confirmée) : {url}")
            return page

    return None


async def deep_search_product(product_name: str, brand: str) -> list[dict]:
    """
    Recherche approfondie : trouve des pages pertinentes depuis PLUSIEURS angles.
    Retourne une liste de pages scrapées, chacune avec son type de source.
    """
    collected_pages = []
    urls_done = set()

    async def _try_scrape(url: str, source_type: str) -> bool:
        """Tente de scraper une URL. Retourne True si réussi."""
        if url in urls_done or not url:
            return False
        urls_done.add(url)
        page = await scrape_product_page(url, product_name)
        if page["success"] and len(page.get("text", "")) > 200:
            page["source_type"] = source_type
            collected_pages.append(page)
            return True
        return False

    async def _search_and_scrape(query: str, source_type: str, max_pages: int = 3) -> int:
        """Recherche + scrape les meilleurs résultats. Retourne le nombre de pages collectées."""
        results = await search_web(query, num_results=8)
        count = 0
        for r in results:
            url = r.get("url", "")
            if count >= max_pages:
                break
            # Pré-filtrer
            if any(bad in url.lower() for bad in ["/s?k=", "/search?", "/recherche?", "google."]):
                continue
            if await _try_scrape(url, source_type):
                count += 1
        return count

    # ─── Stratégie 1 : Page produit officielle du fabricant ───
    print(f"  [SCRAPER] Stratégie 1 : site fabricant {brand}")
    await _search_and_scrape(
        f"{product_name} site officiel {brand}",
        "fabricant", max_pages=1
    )

    # ─── Stratégie 2 : Amazon.fr page produit exacte ───
    print(f"  [SCRAPER] Stratégie 2 : Amazon.fr")
    await _search_and_scrape(
        f"site:amazon.fr {product_name}",
        "amazon", max_pages=2
    )

    # ─── Stratégie 3 : Grandes enseignes françaises ───
    print(f"  [SCRAPER] Stratégie 3 : enseignes françaises")
    french_retailers = ["fnac.com", "decathlon.fr", "boulanger.com", "cdiscount.com", "darty.com"]
    for retailer in french_retailers:
        await _search_and_scrape(
            f"site:{retailer} {product_name}",
            "retailer", max_pages=1
        )
        if len(collected_pages) >= 4:  # Assez de sources retail
            break

    # ─── Stratégie 4 : Sites de test et comparatifs ───
    print(f"  [SCRAPER] Stratégie 4 : tests et avis")
    await _search_and_scrape(
        f"test {product_name} avis complet",
        "test", max_pages=2
    )
    await _search_and_scrape(
        f"{product_name} comparatif review",
        "comparatif", max_pages=1
    )

    # ─── Stratégie 5 : Fiche technique détaillée ───
    print(f"  [SCRAPER] Stratégie 5 : fiches techniques")
    await _search_and_scrape(
        f"{product_name} fiche technique caractéristiques complètes",
        "specs", max_pages=2
    )

    # ─── Stratégie 6 : Comparateurs de prix (pour le prix exact) ───
    print(f"  [SCRAPER] Stratégie 6 : comparateurs de prix")
    await _search_and_scrape(
        f"{product_name} prix comparateur idealo",
        "prix", max_pages=1
    )

    # ─── Stratégie 7 : Recherche générale large (filet de sécurité) ───
    if len(collected_pages) < 3:
        print(f"  [SCRAPER] Stratégie 7 : recherche large (peu de résultats jusque-là)")
        await _search_and_scrape(
            f"{product_name}",
            "general", max_pages=3
        )

    print(f"  [SCRAPER] Total : {len(collected_pages)} pages collectées, {len(urls_done)} URLs testées")
    return collected_pages
