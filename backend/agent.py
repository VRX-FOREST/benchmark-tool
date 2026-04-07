"""
agent.py — Agent IA Deep Research V3.

Trois agents spécialisés :
1. Agent MARCHÉ : analyse le paysage concurrentiel
2. Agent CRITÈRES : sélectionne les critères pertinents (pas de doublons, adaptés au produit)
3. Agent EXTRACTION : extrait et structure les données depuis le texte brut

Règles absolues :
- Chaque produit DOIT avoir une photo et un lien source
- Les critères sont adaptés à la typologie de produit (pas de liste générique)
- Aucune donnée inventée — null si introuvable
"""
import os
import json
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")


def _call_openai(system_prompt: str, user_prompt: str, expect_json: bool = True) -> dict | str:
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


# ══════════════════════════════════════════════
# AGENT 1 : ANALYSE DU MARCHÉ
# ══════════════════════════════════════════════

def research_market_landscape(product_type: str, config: dict) -> dict:
    market = config.get("market", "France")

    system_prompt = f"""Tu es un analyste de marché expert sur le marché {market}.
Analyse cette catégorie de produit pour préparer un benchmark professionnel.

Réponds en JSON :
{{
  "market_overview": "Description du marché (3-4 phrases)",
  "product_nature": "Description technique : de quoi est fait ce produit, comment fonctionne-t-il, à quoi sert-il (3-4 phrases)",
  "segments": [
    {{
      "name": "nom du segment",
      "price_range": "XX - XX €",
      "key_brands": ["marque1", "marque2"],
      "description": "description courte"
    }}
  ],
  "key_purchase_criteria": ["critère d'achat 1", "critère d'achat 2"],
  "technical_differentiators": ["ce qui différencie techniquement les produits entre eux"],
  "leading_brands": [
    {{
      "name": "Marque",
      "position": "leader | challenger | niche",
      "known_models": ["modèle 1", "modèle 2"],
      "strengths": "points forts"
    }}
  ],
  "reference_websites_france": ["site1.com", "site2.com"]
}}"""

    user_prompt = f"""Analyse le marché : **{product_type}**
Marché : {market}

Sois exhaustif sur la nature technique du produit et ce qui différencie les modèles entre eux."""

    return _call_openai(system_prompt, user_prompt)


def select_products(product_type: str, config: dict, market_research: dict = None) -> list[dict]:
    market = config.get("market", "France")
    segment = config.get("segment", "tous")
    max_products = config.get("max_products", 10)

    market_context = ""
    if market_research:
        market_context = f"\nANALYSE DE MARCHÉ :\n{json.dumps(market_research, ensure_ascii=False, indent=2)}\n"

    system_prompt = f"""Tu es un expert benchmark produits pour le marché {market}.
{market_context}

Sélectionne EXACTEMENT {max_products} produits.

RÈGLES :
1. En vente en {market} aujourd'hui (Amazon.fr, Fnac, Decathlon, Cdiscount, Boulanger...)
2. Nom EXACT et COMPLET (marque + modèle + variante)
3. Couvrir TOUS les segments de prix
4. Si une marque a plusieurs modèles importants, en inclure 2-3
5. Pour chaque produit : 3-5 requêtes de recherche FR spécifiques

Réponds en JSON :
{{
  "products": [
    {{
      "name": "Nom EXACT (marque + modèle)",
      "brand": "Marque",
      "segment": "entrée de gamme | milieu de gamme | premium",
      "estimated_price": 99,
      "why_selected": "Justification",
      "search_queries": [
        "site:amazon.fr NomExact",
        "test NomExact avis",
        "NomExact fiche technique"
      ],
      "known_urls": []
    }}
  ]
}}"""

    price_constraint = ""
    if config.get("price_min"):
        price_constraint += f"\n- Prix min : {config['price_min']} €"
    if config.get("price_max"):
        price_constraint += f"\n- Prix max : {config['price_max']} €"

    user_prompt = f"""Benchmark : **{product_type}**
Marché : {market} | Segment : {segment} | Nombre : {max_products}{price_constraint}"""

    result = _call_openai(system_prompt, user_prompt)
    return result.get("products", [])


# ══════════════════════════════════════════════
# AGENT 2 : SÉLECTION DES CRITÈRES (spécialisé)
# ══════════════════════════════════════════════

CRITERIA_BANK = """
BANQUE DE CRITÈRES DE RÉFÉRENCE.
NE PAS TOUS LES PRENDRE. Sélectionner UNIQUEMENT ceux pertinents pour le produit concerné.
AJOUTER des critères spécifiques au produit qui ne figurent pas dans cette banque.

═══ Informations générales ═══
- Marque (text)
- Modèle (text)  
- Prix (number, €)
- Date de lancement (text)
- Positionnement marketing (text)
- Segment de marché (text)

═══ Caractéristiques techniques ═══
Structure produit :
- Dimensions (text)
- Poids (number, g ou kg)
- Architecture du produit (text)
Matériaux :
- Type de matériau (text)
- Densité ou caractéristiques physiques (text)
- Traitements spécifiques (text)
Technologies :
- Technologies intégrées (text)
- Systèmes brevetés (text)
- Innovations techniques (text)
Fabrication :
- Procédé de fabrication (text)
- Pays de fabrication (text)

═══ Fonctionnalités ═══
- Fonctions principales (text)
- Fonctions secondaires (text)
- Bénéfices utilisateurs annoncés (text)

═══ Expérience utilisateur ═══
- Confort (text — description factuelle)
- Ergonomie (text — description factuelle)
- Durabilité (text — description factuelle)
- Facilité d'entretien (text)

═══ Données marché ═══
- Note moyenne clients (number, sur 5)
- Nombre d'avis (number)
- Points positifs récurrents dans les avis (text — synthèse)
- Points négatifs récurrents dans les avis (text — synthèse)
- Distribution (text)
- Canaux de vente (text)
"""


def define_criteria(product_type: str, market_research: dict = None) -> list[dict]:
    """
    Agent CRITÈRES spécialisé.
    
    Son travail est AUSSI IMPORTANT que la recherche elle-même.
    Il sélectionne, adapte et complète les critères pour ce type de produit précis.
    """
    market_context = ""
    if market_research:
        market_context = f"""
CONTEXTE DU PRODUIT (issu de l'analyse de marché) :
- Nature du produit : {market_research.get('product_nature', '')}
- Différenciateurs techniques entre produits : {market_research.get('technical_differentiators', [])}
- Critères d'achat des consommateurs : {market_research.get('key_purchase_criteria', [])}
"""

    system_prompt = f"""Tu es un EXPERT en benchmark de produits physiques.
Ta mission UNIQUE et CRITIQUE : construire la MEILLEURE grille de critères 
pour comparer des **{product_type}**.

{CRITERIA_BANK}

{market_context}

PROCESSUS DE RÉFLEXION :
1. D'abord, comprends ce qu'EST ce produit (matériaux, fonctionnement, usage)
2. Identifie ce qui DIFFÉRENCIE les modèles entre eux
3. Sélectionne dans la banque les critères qui S'APPLIQUENT à ce produit
4. SUPPRIME les critères non pertinents (ex: "Autonomie batterie" pour un rouleau de massage)
5. AJOUTE des critères SPÉCIFIQUES qui manquent dans la banque
   Exemples :
   - Rouleau de massage → Diamètre, Longueur, Surface (lisse/texturée), Niveau de fermeté, Vibration (oui/non)
   - Casque audio → Réduction de bruit active, Codec audio, Autonomie, Pliable
   - Machine à café → Type de café (capsule/grain/moulu), Pression (bars), Capacité réservoir
6. VÉRIFIE qu'il n'y a AUCUN doublon (deux critères mesurant la même chose)

RÈGLES :
- Entre 22 et 32 critères au total
- Noms COURTS (max 5 mots), PRÉCIS
- Chaque critère doit être TROUVABLE sur une fiche produit ou dans des avis en ligne
- Types : "number" (mesurable), "text" (factuel court), "boolean" (oui/non)
- PAS de type "rating" — les notes sont des "number" (sur 5)

Réponds en JSON :
{{
  "criteria_rationale": "Explication de ta logique de sélection (2-3 phrases)",
  "product_specific_additions": ["liste des critères ajoutés spécifiquement pour ce produit"],
  "criteria": [
    {{
      "category": "Informations générales",
      "fields": [
        {{"name": "Prix", "unit": "€", "type": "number"}},
        {{"name": "Marque", "unit": "", "type": "text"}}
      ]
    }},
    {{
      "category": "Caractéristiques techniques",
      "fields": [...]
    }},
    {{
      "category": "Fonctionnalités",
      "fields": [...]
    }},
    {{
      "category": "Expérience utilisateur",
      "fields": [...]
    }},
    {{
      "category": "Données marché",
      "fields": [...]
    }}
  ]
}}"""

    user_prompt = f"""Construis la grille de critères pour : **{product_type}**

Rappel : ton travail sur les critères est AUSSI IMPORTANT que la collecte de données.
Un benchmark avec de mauvais critères est un mauvais benchmark, même avec des données complètes.

Réfléchis : qu'est-ce qu'un acheteur professionnel comparerait pour choisir entre ces produits ?"""

    result = _call_openai(system_prompt, user_prompt)

    criteria = result.get("criteria", [])
    rationale = result.get("criteria_rationale", "")
    additions = result.get("product_specific_additions", [])
    
    if rationale:
        print(f"  [CRITÈRES] Logique : {rationale}")
    if additions:
        print(f"  [CRITÈRES] Critères spécifiques ajoutés : {additions}")

    # Validation : supprimer les doublons éventuels
    seen_names = set()
    for cat in criteria:
        unique_fields = []
        for field in cat.get("fields", []):
            name_lower = field["name"].lower().strip()
            if name_lower not in seen_names:
                seen_names.add(name_lower)
                unique_fields.append(field)
            else:
                print(f"  [CRITÈRES] Doublon supprimé : {field['name']}")
        cat["fields"] = unique_fields

    total = sum(len(c.get("fields", [])) for c in criteria)
    print(f"  [CRITÈRES] Total : {total} critères uniques en {len(criteria)} catégories")

    return criteria


# ══════════════════════════════════════════════
# AGENT 3 : EXTRACTION DES DONNÉES
# ══════════════════════════════════════════════

def structure_scraped_data(product_name: str, raw_text: str, criteria: list[dict], sources: list[str]) -> dict:
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
        f'- Clé: "{f["key"]}" | Type: {f["type"]}' + (f' | Unité: {f["unit"]}' if f["unit"] else '')
        for f in flat_fields
    )

    sources_text = "\n".join(f"  {i+1}. {s}" for i, s in enumerate(sources))

    system_prompt = """Tu es un expert en extraction de données produit.

RÈGLES ABSOLUES :
1. Clés EXACTES (copie-colle)
2. Introuvable → null (JAMAIS inventer)
3. Convertir en métrique / euros
4. "text" → réponse COURTE et FACTUELLE (max 2 phrases)
5. "number" → valeur numérique SEULE
6. "boolean" → true / false / null
7. Pour "Points positifs/négatifs" → synthèse factuelle des avis lus
8. Pour chaque valeur, note l'URL source

Réponds en JSON :
{
  "extracted": { "clé": valeur_ou_null },
  "sources_per_field": { "clé": "URL source" },
  "completeness": 0.65
}"""

    user_prompt = f"""Produit : {product_name}

Sources :
{sources_text}

Critères (clés EXACTES) :
{fields_description}

═══ TEXTE BRUT ═══
{raw_text[:15000]}"""

    return _call_openai(system_prompt, user_prompt)


def deep_extract_missing_fields(
    product_name: str,
    criteria: list[dict],
    existing_data: dict,
    new_text: str,
    new_sources: list[str]
) -> tuple[dict, dict]:
    missing_fields = []
    for cat in criteria:
        for field in cat.get("fields", []):
            unit_str = f" ({field['unit']})" if field.get("unit") else ""
            key = f"{cat['category']} > {field['name']}{unit_str}"
            if existing_data.get(key) is None:
                missing_fields.append({"key": key, "type": field["type"]})

    if not missing_fields:
        return existing_data, {}

    fields_description = "\n".join(f'- "{f["key"]}" ({f["type"]})' for f in missing_fields)

    system_prompt = """Extrais UNIQUEMENT les champs manquants depuis ce nouveau texte.
Clés EXACTES. Introuvable → null. Jamais inventer.

JSON : { "extracted": { "clé": val }, "sources_per_field": { "clé": "url" } }"""

    user_prompt = f"""Produit : {product_name}
Champs MANQUANTS :
{fields_description}

Texte :
{new_text[:12000]}"""

    result = _call_openai(system_prompt, user_prompt)
    new_extracted = result.get("extracted", {})
    merged = {**existing_data}
    for key, val in new_extracted.items():
        if merged.get(key) is None and val is not None:
            merged[key] = val

    return merged, result.get("sources_per_field", {})


def enrich_product_from_knowledge(product_name: str, criteria: list[dict], existing_data: dict) -> dict:
    missing_fields = []
    for cat in criteria:
        if cat["category"] == "Données marché":
            continue
        for field in cat.get("fields", []):
            unit_str = f" ({field['unit']})" if field.get("unit") else ""
            key = f"{cat['category']} > {field['name']}{unit_str}"
            if existing_data.get(key) is None:
                missing_fields.append({"key": key, "type": field["type"]})

    if not missing_fields:
        return existing_data

    fields_description = "\n".join(f'- "{f["key"]}" ({f["type"]})' for f in missing_fields)

    system_prompt = """Complète UNIQUEMENT avec des données FACTUELLES CERTAINES (specs fabricant).
Moindre doute → null. Clés EXACTES. Pas de données marché.
JSON : { "enriched": { "clé": val } }"""

    user_prompt = f"""Produit : {product_name}
Champs manquants (si CERTAIN uniquement) :
{fields_description}"""

    result = _call_openai(system_prompt, user_prompt)
    enriched = result.get("enriched", {})
    merged = {**existing_data}
    for key, val in enriched.items():
        if merged.get(key) is None and val is not None:
            merged[key] = val
    return merged
