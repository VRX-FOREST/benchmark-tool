"""
agent.py — Agent IA pour le benchmark de produits.
Utilise OpenAI GPT-4o via LangGraph pour :
  - Sélectionner les produits pertinents
  - Déterminer les critères de comparaison
  - Structurer les données collectées
"""
import os
import json
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")


def _call_openai(system_prompt: str, user_prompt: str, expect_json: bool = True) -> dict | str:
    """Appel générique à l'API OpenAI."""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    response = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        temperature=0.3,
        response_format={"type": "json_object"} if expect_json else None,
    )

    content = response.choices[0].message.content
    if expect_json:
        return json.loads(content)
    return content


def select_products(product_type: str, config: dict) -> list[dict]:
    """
    Phase 2 : Sélection des produits à comparer.
    Retourne une liste de produits avec nom, marque, et justification.
    """
    system_prompt = """Tu es un expert en analyse de marché de produits physiques.
Tu dois sélectionner les produits les plus pertinents pour un benchmark comparatif.

Critères de sélection :
- Inclure les leaders du marché (incontournables)
- Inclure des challengers et alternatives émergentes
- Couvrir différents segments de prix
- Privilégier les produits actuellement commercialisés
- Chaque produit doit être un modèle précis (marque + référence exacte)

Réponds UNIQUEMENT en JSON avec cette structure :
{
  "products": [
    {
      "name": "Nom complet du produit (marque + modèle)",
      "brand": "Marque",
      "segment": "entrée de gamme | milieu de gamme | premium",
      "why": "Justification courte de la sélection"
    }
  ]
}"""

    user_prompt = f"""Sélectionne les {config.get('max_products', 10)} meilleurs produits 
à inclure dans un benchmark de : {product_type}

Contraintes :
- Marché : {config.get('market', 'France')}
- Segment : {config.get('segment', 'tous')}
- Prix min : {config.get('price_min', 'aucun')}
- Prix max : {config.get('price_max', 'aucun')}"""

    result = _call_openai(system_prompt, user_prompt)
    return result.get("products", [])


def define_criteria(product_type: str) -> list[dict]:
    """
    Phase 3 : Modélisation des critères de comparaison.
    Retourne la grille de critères organisée par catégorie.
    """
    system_prompt = """Tu es un expert en benchmark de produits physiques.
Tu dois définir les critères de comparaison les plus pertinents pour une catégorie de produit donnée.

Organise les critères en catégories. Chaque critère doit avoir :
- Un nom clair et court
- Une unité de mesure si applicable
- Le type de donnée attendu (number, text, boolean, rating)

Réponds UNIQUEMENT en JSON avec cette structure :
{
  "criteria": [
    {
      "category": "Généralités",
      "fields": [
        {"name": "Prix", "unit": "€", "type": "number"},
        {"name": "Date de lancement", "unit": "", "type": "text"}
      ]
    }
  ]
}

Catégories attendues : Généralités, Caractéristiques techniques, Fonctionnalités, 
Expérience utilisateur, Données marché."""

    user_prompt = f"""Définis les critères de comparaison pour un benchmark de : {product_type}

Sois exhaustif mais pertinent. Entre 20 et 40 critères au total, 
répartis sur les 5 catégories."""

    result = _call_openai(system_prompt, user_prompt)
    return result.get("criteria", [])


def structure_scraped_data(product_name: str, raw_text: str, criteria: list[dict]) -> dict:
    """
    Phase 5 : Structure les données brutes collectées en données normalisées.
    Extrait les valeurs correspondant aux critères depuis le texte brut.
    """
    # Construire la liste plate des critères attendus
    flat_criteria = []
    for cat in criteria:
        for field in cat.get("fields", []):
            flat_criteria.append(f"{cat['category']} > {field['name']} ({field.get('unit', '')}) [{field['type']}]")

    criteria_list = "\n".join(f"- {c}" for c in flat_criteria)

    system_prompt = """Tu es un assistant spécialisé dans l'extraction de données produit.
À partir du texte brut fourni (issu du scraping d'une page web), extrais les valeurs 
correspondant aux critères demandés.

Règles strictes :
- Si une donnée n'est PAS clairement présente dans le texte, mets null
- Ne jamais inventer ou deviner une valeur
- Convertir les unités si nécessaire (tout en métrique / euros)
- Pour les prix, extraire le prix actuel constaté
- Pour les notes, extraire la note sur 5

Réponds UNIQUEMENT en JSON avec cette structure :
{
  "extracted": {
    "Nom du critère": valeur_ou_null,
    ...
  },
  "completeness": 0.75  // pourcentage de critères remplis (0.0 à 1.0)
}"""

    user_prompt = f"""Produit : {product_name}

Critères à extraire :
{criteria_list}

Texte brut de la page web :
{raw_text[:8000]}"""

    result = _call_openai(system_prompt, user_prompt)
    return result


def search_product_urls(product_name: str, market: str = "France") -> list[dict]:
    """
    Utilise l'IA pour générer les URLs les plus probables à scraper.
    Retourne une liste d'URLs avec leur type de source.
    """
    system_prompt = """Tu es un expert en recherche de produits en ligne.
Génère les URLs les plus pertinentes pour collecter des informations sur un produit.

Privilégie :
1. La page officielle du fabricant
2. Amazon.fr (ou .com selon le marché)
3. Un site de test spécialisé (Les Numériques, RTings, etc.)
4. Fnac, Cdiscount, ou autre marketplace locale

Réponds UNIQUEMENT en JSON :
{
  "urls": [
    {"url": "https://...", "source_type": "fabricant | marketplace | test | avis", "priority": 1}
  ]
}"""

    user_prompt = f"""Trouve les meilleures URLs pour collecter des données sur :
{product_name}
Marché : {market}
Donne entre 3 et 6 URLs."""

    result = _call_openai(system_prompt, user_prompt)
    return result.get("urls", [])
