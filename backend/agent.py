"""
agent.py — Agent IA Deep Research pour le benchmark de produits.

Philosophie : la qualité prime sur la vitesse.
L'agent procède en plusieurs passes, croise les sources, et ne laisse
aucun champ vide sans avoir épuisé toutes les options de recherche.
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
        temperature=0.2,
        response_format={"type": "json_object"} if expect_json else None,
    )
    content = response.choices[0].message.content
    if expect_json:
        return json.loads(content)
    return content


# ─────────────────────────────────────────────
# PHASE 2 : SÉLECTION DES PRODUITS (Deep)
# ─────────────────────────────────────────────

def research_market_landscape(product_type: str, config: dict) -> dict:
    """
    Étape préliminaire : comprendre le marché avant de sélectionner.
    L'IA analyse la catégorie pour identifier les segments, les marques clés,
    et les critères d'achat principaux.
    """
    market = config.get("market", "France")

    system_prompt = f"""Tu es un analyste de marché expert, spécialisé sur le marché {market}.
On te demande une analyse préliminaire d'une catégorie de produit AVANT de sélectionner 
des produits pour un benchmark comparatif.

Réponds en JSON :
{{
  "market_overview": "Description courte du marché (3-4 phrases)",
  "segments": [
    {{
      "name": "Nom du segment (ex: entrée de gamme, premium, professionnel)",
      "price_range": "fourchette de prix en €",
      "key_brands": ["marque1", "marque2"],
      "description": "description courte"
    }}
  ],
  "key_purchase_criteria": ["critère 1", "critère 2"],
  "leading_brands": [
    {{
      "name": "Marque",
      "position": "leader | challenger | niche | entrée de gamme",
      "strengths": "points forts en 1 phrase"
    }}
  ],
  "reference_websites_france": ["site1.com", "site2.com"]
}}"""

    user_prompt = f"""Analyse le marché suivant : **{product_type}**
Marché géographique : {market}

Identifie tous les segments de prix, les marques incontournables,
et les sites de référence pour trouver des tests et avis en France."""

    return _call_openai(system_prompt, user_prompt)


def select_products(product_type: str, config: dict, market_research: dict = None) -> list[dict]:
    """
    Phase 2 : Sélection des produits — version Deep Research.
    Utilise l'analyse de marché préliminaire pour une sélection informée.
    """
    market = config.get("market", "France")
    segment = config.get("segment", "tous")
    max_products = config.get("max_products", 10)

    # Contexte de marché si disponible
    market_context = ""
    if market_research:
        market_context = f"""
CONTEXTE DE MARCHÉ (issu de ton analyse préliminaire) :
- Vue d'ensemble : {market_research.get('market_overview', '')}
- Segments identifiés : {json.dumps(market_research.get('segments', []), ensure_ascii=False)}
- Marques leaders : {json.dumps(market_research.get('leading_brands', []), ensure_ascii=False)}
- Sites de référence : {market_research.get('reference_websites_france', [])}

Utilise ces informations pour faire une sélection EXHAUSTIVE et REPRÉSENTATIVE.
"""

    system_prompt = f"""Tu es un expert benchmark produits pour le marché {market}.
{market_context}

Ta mission : sélectionner EXACTEMENT {max_products} produits pour un benchmark professionnel.

CRITÈRES DE SÉLECTION (par ordre de priorité) :
1. REPRÉSENTATIVITÉ : le benchmark doit couvrir TOUS les segments de prix identifiés
2. DISPONIBILITÉ : chaque produit DOIT être actuellement en vente en {market}
   (vérifiable sur Amazon.fr, Fnac.fr, Decathlon.fr, Cdiscount, Boulanger, site officiel)
3. POPULARITÉ : privilégier les produits avec beaucoup d'avis (best-sellers)
4. PERTINENCE : chaque produit doit être un concurrent direct des autres
5. DIVERSITÉ DES MARQUES : couvrir les leaders ET les challengers
6. Si une marque domine le marché avec plusieurs modèles pertinents (ex: Decathlon pour le sport),
   inclure 2-3 de ses modèles

RÈGLES STRICTES :
- Nom de modèle EXACT et COMPLET (pas de nom générique ou approximatif)
- Pour chaque produit, fournis 3-5 requêtes de recherche spécifiques en français
  (une pour Amazon, une pour un site de test, une pour le site officiel, etc.)
- Indique l'URL exacte si tu la connais (sinon laisse vide)

Réponds en JSON :
{{
  "selection_rationale": "Explication de ta logique de sélection (2-3 phrases)",
  "products": [
    {{
      "name": "Nom EXACT complet (marque + modèle + variante si pertinent)",
      "brand": "Marque",
      "segment": "entrée de gamme | milieu de gamme | premium | professionnel",
      "estimated_price": 99,
      "why_selected": "Pourquoi ce produit et pas un autre de la même marque",
      "search_queries": [
        "requête recherche 1 (ex: amazon.fr NomProduit)",
        "requête recherche 2 (ex: test NomProduit lesnumeriques)",
        "requête recherche 3 (ex: NomProduit fiche technique)"
      ],
      "known_urls": ["https://url-si-connue.com"]
    }}
  ]
}}"""

    price_constraint = ""
    if config.get("price_min"):
        price_constraint += f"\n- Prix minimum : {config['price_min']} €"
    if config.get("price_max"):
        price_constraint += f"\n- Prix maximum : {config['price_max']} €"

    user_prompt = f"""Benchmark professionnel de : **{product_type}**

Contraintes :
- Marché : {market}
- Segment : {segment}
- Nombre de produits : exactement {max_products}{price_constraint}

Sélectionne les {max_products} produits les plus pertinents.
Justifie chaque choix."""

    result = _call_openai(system_prompt, user_prompt)
    return result.get("products", [])


# ─────────────────────────────────────────────
# PHASE 3 : CRITÈRES DE COMPARAISON (Deep)
# ─────────────────────────────────────────────

def define_criteria(product_type: str, market_research: dict = None) -> list[dict]:
    """
    Phase 3 : Modélisation des critères — version Deep Research.
    S'appuie sur l'analyse de marché pour des critères vraiment pertinents.
    """
    market_context = ""
    if market_research:
        market_context = f"""
Critères d'achat identifiés par l'analyse de marché : 
{market_research.get('key_purchase_criteria', [])}
Intègre-les dans ta grille de critères.
"""

    system_prompt = f"""Tu es un expert en benchmark de produits physiques.
{market_context}

Définis les critères de comparaison pour un benchmark PROFESSIONNEL.

RÈGLES :
1. Entre 25 et 40 critères, répartis équitablement entre les catégories
2. Noms COURTS (max 4 mots), PRÉCIS et NON AMBIGUS
3. Privilégie les critères FACTUELS, MESURABLES et VÉRIFIABLES sur le web
4. Inclus les critères que les sites de test (Les Numériques, RTings, etc.) utilisent
5. Chaque critère doit être discriminant (permettre de différencier les produits)
6. Ne PAS inclure de critères redondants

Types de données :
- "number" : valeur numérique (poids, prix, autonomie...)
- "text" : texte court factuel (matériau, pays de fabrication...)
- "boolean" : oui/non (présence d'une fonctionnalité)
- "rating" : note sur 5

Réponds en JSON :
{{
  "criteria": [
    {{
      "category": "Généralités",
      "fields": [
        {{"name": "Prix", "unit": "€", "type": "number"}},
        {{"name": "Date de sortie", "unit": "", "type": "text"}}
      ]
    }}
  ]
}}

Catégories obligatoires : Généralités, Caractéristiques techniques, 
Fonctionnalités, Expérience utilisateur, Données marché."""

    user_prompt = f"Critères de comparaison professionnels pour : {product_type}"

    result = _call_openai(system_prompt, user_prompt)
    return result.get("criteria", [])


# ─────────────────────────────────────────────
# PHASE 5 : EXTRACTION DES DONNÉES (Deep)
# ─────────────────────────────────────────────

def structure_scraped_data(product_name: str, raw_text: str, criteria: list[dict], sources: list[str]) -> dict:
    """
    Phase 5 : Extraction des données depuis le texte brut.
    Version améliorée : passe la liste des sources pour traçabilité.
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

    sources_list = "\n".join(f"- {s}" for s in sources)

    system_prompt = """Tu es un analyste produit expert. Tu extrais des données FACTUELLES 
depuis du texte brut issu du scraping de plusieurs pages web.

RÈGLES STRICTES :
1. Utilise EXACTEMENT les clés fournies (copie-colle)
2. Si la donnée n'est PAS clairement dans le texte → null
3. JAMAIS inventer ou deviner une valeur
4. Convertir en métrique (grammes, mm) et en euros
5. Si plusieurs sources donnent des valeurs différentes, prends la plus récente ou la plus fiable
6. Pour chaque valeur trouvée, note l'URL source dans le champ "sources"

Réponds en JSON :
{
  "extracted": {
    "clé exacte 1": valeur_ou_null,
    "clé exacte 2": valeur_ou_null
  },
  "sources_per_field": {
    "clé exacte 1": "url-de-la-source",
    "clé exacte 2": "url-de-la-source"
  },
  "completeness": 0.65
}"""

    user_prompt = f"""Produit : {product_name}

Sources scrappées :
{sources_list}

Clés à extraire (EXACTEMENT ces clés) :
{fields_description}

Texte brut combiné des pages web :
{raw_text[:12000]}"""

    result = _call_openai(system_prompt, user_prompt)
    return result


def deep_extract_missing_fields(
    product_name: str, 
    criteria: list[dict], 
    existing_data: dict,
    new_text: str,
    new_sources: list[str]
) -> dict:
    """
    Passe d'extraction complémentaire : cherche UNIQUEMENT les champs manquants
    dans un nouveau texte scrapé.
    """
    missing_fields = []
    for cat in criteria:
        for field in cat.get("fields", []):
            unit_str = f" ({field['unit']})" if field.get("unit") else ""
            key = f"{cat['category']} > {field['name']}{unit_str}"
            if existing_data.get(key) is None:
                missing_fields.append({
                    "key": key,
                    "type": field["type"],
                    "unit": field.get("unit", ""),
                })

    if not missing_fields:
        return existing_data

    fields_description = "\n".join(
        f'- "{f["key"]}" (type: {f["type"]})'
        for f in missing_fields
    )

    system_prompt = """Tu extrais des données FACTUELLES depuis du texte brut.
On te donne UNIQUEMENT les champs qui sont encore manquants.

RÈGLES :
1. Clés EXACTES
2. Si pas dans le texte → null
3. Jamais inventer

Réponds en JSON :
{
  "extracted": { "clé": valeur_ou_null },
  "sources_per_field": { "clé": "url-source" }
}"""

    user_prompt = f"""Produit : {product_name}

Champs MANQUANTS à chercher :
{fields_description}

Nouveau texte à analyser :
{new_text[:10000]}"""

    result = _call_openai(system_prompt, user_prompt)
    
    # Fusionner avec les données existantes
    new_extracted = result.get("extracted", {})
    merged = {**existing_data}
    for key, val in new_extracted.items():
        if merged.get(key) is None and val is not None:
            merged[key] = val

    return merged, result.get("sources_per_field", {})


def enrich_product_from_knowledge(product_name: str, criteria: list[dict], existing_data: dict) -> dict:
    """
    DERNIER RECOURS : complète avec les connaissances de l'IA.
    Uniquement pour les données factuelles vérifiables (specs techniques).
    """
    missing_fields = []
    for cat in criteria:
        for field in cat.get("fields", []):
            unit_str = f" ({field['unit']})" if field.get("unit") else ""
            key = f"{cat['category']} > {field['name']}{unit_str}"
            if existing_data.get(key) is None:
                missing_fields.append({"key": key, "type": field["type"]})

    if not missing_fields:
        return existing_data

    # Ne demander que les données factuelles (pas les ratings ni données marché)
    factual_fields = [f for f in missing_fields 
                      if "Données marché" not in f["key"] 
                      and f["type"] != "rating"]

    if not factual_fields:
        return existing_data

    fields_description = "\n".join(f'- "{f["key"]}" ({f["type"]})' for f in factual_fields)

    system_prompt = """Tu es un expert produit. Complète les données manquantes 
UNIQUEMENT avec des informations FACTUELLES dont tu es CERTAIN.

RÈGLES ULTRA-STRICTES :
1. Ne fournis QUE les données que tu connais avec certitude (specs officielles du fabricant)
2. Si tu as le moindre doute → null
3. Clés EXACTES
4. Mieux vaut 5 données sûres que 20 approximations

Réponds en JSON :
{
  "enriched": { "clé": valeur_ou_null },
  "confidence": "high | medium"
}"""

    user_prompt = f"""Produit : {product_name}

Champs factuels manquants à compléter SI tu es certain :
{fields_description}"""

    result = _call_openai(system_prompt, user_prompt)
    enriched = result.get("enriched", {})

    merged = {**existing_data}
    for key, val in enriched.items():
        if merged.get(key) is None and val is not None:
            merged[key] = val

    return merged
