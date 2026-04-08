"""
agent.py — Agent IA Deep Research V7.

NOUVEAU FLOW DE SÉLECTION :
1. Étude de marché RÉELLE (recherche web) — pas juste les connaissances de l'IA
2. Compilation des produits les plus cités/recommandés sur le web français
3. Sélection informée basée sur les données réelles du marché
4. Critères adaptés au produit

L'IA ne "devine" plus les produits — elle les TROUVE sur le web.
"""
import os
import json
import re
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


def _web_search(query: str) -> dict:
    """OpenAI web search."""
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
        return {"success": False, "text": "", "sources": []}


# ══════════════════════════════════════════════
# PHASE 1 : ÉTUDE DE MARCHÉ RÉELLE (web search)
# ══════════════════════════════════════════════

def research_market_landscape(product_type: str, config: dict) -> dict:
    """
    Étude de marché RÉELLE basée sur des recherches web.
    L'agent cherche les comparatifs, classements et tests existants
    pour identifier les vrais produits de référence du marché.
    """
    market = config.get("market", "France")
    print(f"  [MARCHÉ] Début de l'étude de marché : {product_type}")

    # ── Recherche 1 : Comparatifs et classements récents ──
    print(f"  [MARCHÉ] Recherche des comparatifs et classements...")
    comparatifs = _web_search(
        f"meilleur {product_type} 2025 2024 comparatif classement France test. "
        f"Quels sont les produits les plus recommandés ? "
        f"Donne les noms EXACTS des produits (marque + modèle) cités dans les classements."
    )

    # ── Recherche 2 : Best-sellers et produits populaires ──
    print(f"  [MARCHÉ] Recherche des best-sellers...")
    bestsellers = _web_search(
        f"best seller {product_type} amazon.fr meilleures ventes France 2025. "
        f"Quels sont les produits les plus vendus ? "
        f"Noms EXACTS des produits (marque + modèle)."
    )

    # ── Recherche 3 : Marques et acteurs du marché ──
    print(f"  [MARCHÉ] Recherche des marques de référence...")
    brands = _web_search(
        f"marques {product_type} référence France. "
        f"Quelles sont les marques leaders, challengers et alternatives ? "
        f"Pour chaque marque, quels sont leurs modèles principaux ?"
    )

    # ── Recherche 4 : Guides d'achat (critères clés) ──
    print(f"  [MARCHÉ] Recherche des guides d'achat...")
    guides = _web_search(
        f"guide achat {product_type} comment choisir critères importants. "
        f"Quels sont les critères de choix les plus importants selon les experts ?"
    )

    # ── Synthèse par l'IA ──
    print(f"  [MARCHÉ] Synthèse des résultats...")

    all_research = f"""
═══ COMPARATIFS ET CLASSEMENTS ═══
{comparatifs.get('text', '')}

═══ BEST-SELLERS ═══
{bestsellers.get('text', '')}

═══ MARQUES ET ACTEURS ═══
{brands.get('text', '')}

═══ GUIDES D'ACHAT ═══
{guides.get('text', '')}
"""

    synthesis = _call_openai(
        f"""Tu es un analyste de marché. À partir des recherches web ci-dessous,
synthétise une étude de marché complète pour "{product_type}" sur le marché {market}.

IMPORTANT : base-toi UNIQUEMENT sur les données trouvées dans les recherches web.
Ne rajoute PAS de produits ou marques que tu ne vois pas dans les résultats.

Réponds en JSON :
{{
  "market_overview": "Vue d'ensemble du marché (3-4 phrases)",
  "product_nature": "Description du produit : matériaux, fonctionnement, usage (3-4 phrases)",
  "segments": [
    {{
      "name": "nom du segment",
      "price_range": "XX - XX €",
      "description": "description"
    }}
  ],
  "products_found_in_rankings": [
    {{
      "name": "Nom EXACT du produit (marque + modèle) tel que trouvé dans les classements",
      "brand": "Marque",
      "times_mentioned": 3,
      "context": "Dans quel classement/comparatif ce produit a été trouvé",
      "estimated_price": 49,
      "segment": "entrée de gamme | milieu de gamme | premium"
    }}
  ],
  "leading_brands": [
    {{
      "name": "Marque",
      "position": "leader | challenger | niche",
      "known_models": ["modèle 1", "modèle 2"],
      "strengths": "points forts"
    }}
  ],
  "key_purchase_criteria": ["critère 1", "critère 2"],
  "technical_differentiators": ["ce qui différencie les produits"],
  "reference_sources": ["site1.com", "site2.com"]
}}

RÈGLE : la liste "products_found_in_rankings" doit contenir TOUS les produits
mentionnés dans les comparatifs et classements, triés par nombre de mentions (les plus cités en premier).
""",
        f"Résultats des recherches web :\n{all_research}"
    )

    # Compiler les sources
    all_sources = []
    for r in [comparatifs, bestsellers, brands, guides]:
        all_sources.extend(r.get("sources", []))
    synthesis["research_sources"] = all_sources

    products_found = synthesis.get("products_found_in_rankings", [])
    print(f"  [MARCHÉ] Synthèse : {len(products_found)} produits trouvés dans les classements")
    for p in products_found[:5]:
        print(f"    → {p['name']} ({p.get('times_mentioned', '?')} mentions)")

    return synthesis


# ══════════════════════════════════════════════
# PHASE 2 : SÉLECTION INFORMÉE
# ══════════════════════════════════════════════

def select_products(product_type: str, config: dict, market_research: dict = None) -> list[dict]:
    """
    Sélection basée sur l'étude de marché RÉELLE.
    Priorité aux produits TROUVÉS dans les classements web, pas devinés par l'IA.
    """
    market = config.get("market", "France")
    max_products = config.get("max_products", 12)

    products_from_rankings = []
    if market_research:
        products_from_rankings = market_research.get("products_found_in_rankings", [])

    if products_from_rankings:
        # On a des vrais produits trouvés sur le web → les utiliser en priorité
        print(f"  [SÉLECTION] {len(products_from_rankings)} produits trouvés dans les classements web")

        system_prompt = f"""Tu es un expert benchmark produits.
Tu as reçu une liste de produits RÉELLEMENT trouvés dans des comparatifs et classements web.
Ta mission : sélectionner les {max_products} meilleurs pour un benchmark professionnel.

RÈGLES :
1. PRIVILÉGIE les produits de la liste (ils sont confirmés par le web)
2. Tu peux en ajouter 1-2 si un segment important n'est pas couvert
3. Les produits les plus cités (times_mentioned élevé) ont la priorité
4. Couvre tous les segments de prix
5. Noms EXACTS tels que trouvés dans les classements

Réponds en JSON :
{{
  "products": [
    {{
      "name": "Nom EXACT",
      "brand": "Marque",
      "segment": "entrée de gamme | milieu de gamme | premium",
      "estimated_price": 49,
      "why_selected": "Cité dans X comparatifs, best-seller Amazon, etc.",
      "from_web_research": true,
      "search_queries": ["query 1", "query 2"]
    }}
  ]
}}"""

        price_constraint = ""
        if config.get("price_min"):
            price_constraint += f"\n- Prix min : {config['price_min']} €"
        if config.get("price_max"):
            price_constraint += f"\n- Prix max : {config['price_max']} €"

        user_prompt = f"""Benchmark : {product_type} | Marché : {market} | Nombre : {max_products}{price_constraint}

Produits trouvés dans les classements web (triés par nombre de mentions) :
{json.dumps(products_from_rankings, ensure_ascii=False, indent=2)}

Marques identifiées :
{json.dumps(market_research.get('leading_brands', []), ensure_ascii=False, indent=2)}

Sélectionne les {max_products} plus pertinents."""

        result = _call_openai(system_prompt, user_prompt)
        return result.get("products", [])

    else:
        # Fallback : pas d'étude de marché, sélection classique
        print(f"  [SÉLECTION] Pas de données web, sélection classique")
        return _select_products_classic(product_type, config)


def _select_products_classic(product_type: str, config: dict) -> list[dict]:
    """Sélection classique sans étude de marché (fallback)."""
    market = config.get("market", "France")
    max_products = config.get("max_products", 12)

    system_prompt = f"""Sélectionne {max_products} produits pour un benchmark de {product_type} en {market}.
Noms EXACTS, en vente actuellement.
JSON : {{"products": [{{"name": "...", "brand": "...", "segment": "...", "estimated_price": 99, "why_selected": "...", "search_queries": ["..."]}}]}}"""

    result = _call_openai(system_prompt, f"Benchmark : {product_type}")
    return result.get("products", [])


# ══════════════════════════════════════════════
# PHASE 3 : CRITÈRES DE COMPARAISON
# ══════════════════════════════════════════════

CRITERIA_BANK = """
BANQUE DE CRITÈRES DE RÉFÉRENCE.
NE PAS TOUS LES PRENDRE. Sélectionner UNIQUEMENT ceux pertinents pour le produit.
AJOUTER des critères spécifiques qui manquent.

═══ Informations générales ═══
- Marque (text) | Modèle (text) | Prix (number, €) | Date de lancement (text)
- Positionnement marketing (text) | Segment de marché (text)

═══ Caractéristiques techniques ═══
- Dimensions (text) | Poids (number, g ou kg) | Architecture du produit (text)
- Type de matériau (text) | Densité (text) | Traitements spécifiques (text)
- Technologies intégrées (text) | Systèmes brevetés (text) | Innovations techniques (text)
- Procédé de fabrication (text) | Pays de fabrication (text)

═══ Fonctionnalités ═══
- Fonctions principales (text) | Fonctions secondaires (text)
- Bénéfices utilisateurs annoncés (text)

═══ Expérience utilisateur ═══
- Confort (text) | Ergonomie (text) | Durabilité (text) | Facilité d'entretien (text)

═══ Données marché ═══
- Note moyenne clients (number, sur 5) | Nombre d'avis (number)
- Points positifs récurrents (text) | Points négatifs récurrents (text)
- Distribution (text) | Canaux de vente (text)
"""


def define_criteria(product_type: str, market_research: dict = None) -> list[dict]:
    """Agent critères spécialisé."""
    market_context = ""
    if market_research:
        market_context = f"""
CONTEXTE :
- Nature du produit : {market_research.get('product_nature', '')}
- Différenciateurs : {market_research.get('technical_differentiators', [])}
- Critères d'achat : {market_research.get('key_purchase_criteria', [])}
"""

    system_prompt = f"""Expert benchmark produits physiques.
{CRITERIA_BANK}
{market_context}

PROCESSUS :
1. Comprends ce qu'EST le produit
2. Identifie ce qui DIFFÉRENCIE les modèles
3. Sélectionne les critères pertinents dans la banque
4. AJOUTE des critères SPÉCIFIQUES au produit
5. AUCUN doublon
6. 22-32 critères, noms COURTS (max 5 mots)
7. Types : "number", "text", "boolean"

JSON :
{{
  "criteria_rationale": "explication",
  "product_specific_additions": ["critère ajouté 1"],
  "criteria": [
    {{
      "category": "Informations générales",
      "fields": [{{"name": "Prix", "unit": "€", "type": "number"}}]
    }}
  ]
}}

Catégories : Informations générales, Caractéristiques techniques, Fonctionnalités, Expérience utilisateur, Données marché."""

    result = _call_openai(system_prompt, f"Critères pour : {product_type}")

    criteria = result.get("criteria", [])
    additions = result.get("product_specific_additions", [])
    if additions:
        print(f"  [CRITÈRES] Ajouts spécifiques : {additions}")

    # Anti-doublons
    seen = set()
    for cat in criteria:
        unique = []
        for f in cat.get("fields", []):
            name_lower = f["name"].lower().strip()
            if name_lower not in seen:
                seen.add(name_lower)
                unique.append(f)
        cat["fields"] = unique

    total = sum(len(c.get("fields", [])) for c in criteria)
    print(f"  [CRITÈRES] {total} critères uniques")
    return criteria


# ══════════════════════════════════════════════
# EXTRACTION DES DONNÉES
# ══════════════════════════════════════════════

def structure_scraped_data(product_name: str, raw_text: str, criteria: list[dict], sources: list[str]) -> dict:
    flat_fields = []
    for cat in criteria:
        for field in cat.get("fields", []):
            unit_str = f" ({field['unit']})" if field.get("unit") else ""
            flat_fields.append({"key": f"{cat['category']} > {field['name']}{unit_str}", "type": field["type"]})

    fields_desc = "\n".join(f'- "{f["key"]}" ({f["type"]})' for f in flat_fields)
    sources_text = "\n".join(f"  {i+1}. {s}" for i, s in enumerate(sources[:15]))

    system_prompt = """Expert extraction de données produit.
RÈGLES : clés EXACTES, introuvable → null, jamais inventer, convertir métrique/euros.
JSON : {"extracted": {"clé": val}, "sources_per_field": {"clé": "url"}, "completeness": 0.65}"""

    user_prompt = f"""Produit : {product_name}\nSources :\n{sources_text}\nCritères :\n{fields_desc}\n\n{raw_text[:15000]}"""
    return _call_openai(system_prompt, user_prompt)


def deep_extract_missing_fields(product_name, criteria, existing_data, new_text, new_sources):
    missing = []
    for cat in criteria:
        for f in cat.get("fields", []):
            unit_str = f" ({f['unit']})" if f.get("unit") else ""
            key = f"{cat['category']} > {f['name']}{unit_str}"
            if existing_data.get(key) is None:
                missing.append({"key": key, "type": f["type"]})
    if not missing:
        return existing_data, {}
    fields_desc = "\n".join(f'- "{f["key"]}" ({f["type"]})' for f in missing)
    system_prompt = """Extrais UNIQUEMENT les champs manquants. Clés EXACTES, null si introuvable.
JSON : {"extracted": {"clé": val}, "sources_per_field": {"clé": "url"}}"""
    result = _call_openai(system_prompt, f"Produit : {product_name}\nManquants :\n{fields_desc}\n\n{new_text[:12000]}")
    merged = {**existing_data}
    for k, v in result.get("extracted", {}).items():
        if merged.get(k) is None and v is not None:
            merged[k] = v
    return merged, result.get("sources_per_field", {})


def enrich_product_from_knowledge(product_name, criteria, existing_data):
    missing = []
    for cat in criteria:
        if cat["category"] == "Données marché":
            continue
        for f in cat.get("fields", []):
            unit_str = f" ({f['unit']})" if f.get("unit") else ""
            key = f"{cat['category']} > {f['name']}{unit_str}"
            if existing_data.get(key) is None:
                missing.append({"key": key, "type": f["type"]})
    if not missing:
        return existing_data
    fields_desc = "\n".join(f'- "{f["key"]}" ({f["type"]})' for f in missing)
    system_prompt = """Complète avec données FACTUELLES CERTAINES uniquement. Moindre doute → null.
JSON : {"enriched": {"clé": val}}"""
    result = _call_openai(system_prompt, f"Produit : {product_name}\nManquants :\n{fields_desc}")
    merged = {**existing_data}
    for k, v in result.get("enriched", {}).items():
        if merged.get(k) is None and v is not None:
            merged[k] = v
    return merged
