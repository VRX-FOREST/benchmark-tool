"""
agent.py — Agent IA pour le benchmark de produits.
Utilise OpenAI GPT-4o pour :
  - Sélectionner les produits pertinents (V2 améliorée)
  - Déterminer les critères de comparaison
  - Structurer les données collectées
  - Extraire des données même sans scraping (fallback connaissances)
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
    Améliorée : focus sur les produits réellement disponibles sur le marché cible.
    """
    market = config.get("market", "France")
    segment = config.get("segment", "tous")
    max_products = config.get("max_products", 10)

    system_prompt = f"""Tu es un expert en analyse de marché de produits physiques, 
spécialisé sur le marché {market}.

Ta mission : sélectionner les {max_products} produits les plus pertinents pour un benchmark comparatif.

RÈGLES STRICTES :
1. Chaque produit DOIT être actuellement en vente en {market} (vérifie mentalement qu'on le trouve sur Amazon.fr, Fnac.fr, Decathlon.fr, Cdiscount.fr, ou le site officiel de la marque)
2. Chaque produit DOIT avoir un nom de modèle PRÉCIS et EXACT (pas de nom générique)
3. Privilégie les produits avec beaucoup d'avis en ligne (populaires)
4. Inclus un MIX de :
   - 2-3 leaders incontournables (best-sellers)
   - 2-3 challengers (bon rapport qualité-prix)
   - 2-3 alternatives (entrée de gamme ou niche)
5. Si une marque a plusieurs modèles pertinents, inclus les 2-3 meilleurs, pas un seul
6. NE PAS inclure de produits obscurs, arrêtés, ou introuvables en {market}

Pour chaque produit, fournis une URL de recherche Google Shopping France.

Réponds UNIQUEMENT en JSON :
{{
  "products": [
    {{
      "name": "Nom EXACT du produit (marque + modèle précis)",
      "brand": "Marque",
      "segment": "entrée de gamme | milieu de gamme | premium",
      "estimated_price": 99,
      "search_query": "requête Google optimale pour trouver ce produit en France",
      "why": "Justification courte"
    }}
  ]
}}"""

    price_constraint = ""
    if config.get("price_min"):
        price_constraint += f"\n- Prix minimum : {config['price_min']} €"
    if config.get("price_max"):
        price_constraint += f"\n- Prix maximum : {config['price_max']} €"

    user_prompt = f"""Sélectionne les {max_products} meilleurs produits pour un benchmark de :
**{product_type}**

Contraintes :
- Marché : {market}
- Segment : {segment}{price_constraint}

IMPORTANT : Ne choisis QUE des produits que tu es CERTAIN de trouver en vente en {market} aujourd'hui.
Privilégie les modèles populaires avec beaucoup d'avis."""

    result = _call_openai(system_prompt, user_prompt)
    return result.get("products", [])


def define_criteria(product_type: str) -> list[dict]:
    """
    Phase 3 : Modélisation des critères de comparaison.
    """
    system_prompt = """Tu es un expert en benchmark de produits physiques.
Définis les critères de comparaison les plus pertinents pour une catégorie de produit.

RÈGLES :
1. Entre 20 et 35 critères au total
2. Chaque critère doit avoir un nom COURT et SIMPLE (max 4 mots)
3. Utilise des noms standards et non ambigus
4. Privilégie les critères FACTUELS et MESURABLES (pas de critères subjectifs vagues)

Réponds UNIQUEMENT en JSON :
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

Catégories : Généralités, Caractéristiques techniques, Fonctionnalités, 
Expérience utilisateur, Données marché."""

    user_prompt = f"Définis les critères de comparaison pour : {product_type}"

    result = _call_openai(system_prompt, user_prompt)
    return result.get("criteria", [])


def structure_scraped_data(product_name: str, raw_text: str, criteria: list[dict]) -> dict:
    """
    Phase 5 : Extrait les données depuis le texte brut du scraping.
    Utilise les noms de champs EXACTS des critères comme clés.
    """
    flat_fields = []
    for cat in criteria:
        for field in cat.get("fields", []):
            unit_str = f" ({field['unit']})" if field.get("unit") else ""
            flat_fields.append({
                "key": f"{cat['category']} > {field['name']}{unit_str}",
                "name": field["name"],
                "unit": field.get("unit", ""),
                "type": field["type"],
            })

    fields_description = "\n".join(
        f'- Clé: "{f["key"]}" | Type: {f["type"]} | Unité: {f["unit"] or "aucune"}'
        for f in flat_fields
    )

    system_prompt = """Tu es un assistant spécialisé dans l'extraction de données produit.

RÈGLES STRICTES :
1. Utilise EXACTEMENT les clés fournies (copie-colle, ne reformule pas)
2. Si une donnée n'est PAS clairement dans le texte → null
3. Ne JAMAIS inventer une valeur
4. Convertir en métrique et en euros si nécessaire
5. Pour les booléens : true/false/null
6. Pour les nombres : valeur numérique sans unité
7. Pour les textes : valeur courte et factuelle

Réponds UNIQUEMENT en JSON :
{
  "extracted": {
    "clé exacte 1": valeur_ou_null,
    "clé exacte 2": valeur_ou_null
  },
  "completeness": 0.45
}"""

    user_prompt = f"""Produit : {product_name}

Clés à utiliser (EXACTEMENT ces clés, ne pas modifier) :
{fields_description}

Texte brut des pages web :
{raw_text[:10000]}"""

    result = _call_openai(system_prompt, user_prompt)
    return result


def enrich_product_from_knowledge(product_name: str, criteria: list[dict], existing_data: dict) -> dict:
    """
    FALLBACK : Si le scraping a peu de résultats, complète avec les connaissances de l'IA.
    Les données ajoutées sont marquées comme "source: IA" pour transparence.
    """
    # Compter les champs déjà remplis
    filled = sum(1 for v in existing_data.values() if v is not None)
    total_fields = sum(len(cat.get("fields", [])) for cat in criteria)

    # Si déjà plus de 50% rempli, pas besoin d'enrichir
    if total_fields > 0 and (filled / total_fields) > 0.5:
        return existing_data

    flat_fields = []
    for cat in criteria:
        for field in cat.get("fields", []):
            unit_str = f" ({field['unit']})" if field.get("unit") else ""
            key = f"{cat['category']} > {field['name']}{unit_str}"
            # Ne demander que les champs manquants
            if existing_data.get(key) is None:
                flat_fields.append({
                    "key": key,
                    "type": field["type"],
                    "unit": field.get("unit", ""),
                })

    if not flat_fields:
        return existing_data

    fields_description = "\n".join(
        f'- "{f["key"]}" (type: {f["type"]})'
        for f in flat_fields
    )

    system_prompt = """Tu es un expert produit. On te demande de compléter des données manquantes 
sur un produit à partir de tes connaissances.

RÈGLES :
1. Ne fournis QUE les données dont tu es CERTAIN (produits connus et vérifiables)
2. Si tu n'es pas sûr → null
3. Utilise EXACTEMENT les clés fournies
4. Mieux vaut null qu'une donnée fausse

Réponds en JSON :
{
  "enriched": {
    "clé exacte": valeur_ou_null
  }
}"""

    user_prompt = f"""Produit : {product_name}

Champs manquants à compléter si tu les connais avec certitude :
{fields_description}"""
    result = _call_openai(system_prompt, user_prompt)
    enriched = result.get("enriched", {})

    # Fusionner : garder les données scrapées, ajouter les enrichissements IA
    merged = {**existing_data}
    for key, val in enriched.items():
        if merged.get(key) is None and val is not None:
            merged[key] = val

    return merged
