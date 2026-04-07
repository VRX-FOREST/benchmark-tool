"""
database.py — Stockage des données via Redis.

Pourquoi Redis et pas SQLite ?
Sur Railway, le backend (FastAPI) et le worker (Celery) tournent dans des
conteneurs SÉPARÉS. Ils ne partagent pas de fichier sur disque.
En revanche, ils sont TOUS LES DEUX connectés au même service Redis.
Redis devient donc la base de données partagée.

Structure des clés Redis :
  - benchmark:{id}          → JSON du benchmark (config, critères, statut)
  - benchmark:{id}:products → JSON de la liste des produits
  - benchmarks:index        → Liste ordonnée des IDs de benchmarks
"""
import os
import json
import redis
from datetime import datetime

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

_redis_client = None


def _get_redis():
    """Connexion Redis réutilisable."""
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    return _redis_client


def init_db():
    """Vérifie la connexion Redis. Pas de tables à créer."""
    r = _get_redis()
    r.ping()
    print("[DB] Connexion Redis OK")


# ─── BENCHMARKS ───


def create_benchmark(benchmark_id: str, product_type: str, config: dict) -> dict:
    """Crée un nouveau benchmark."""
    r = _get_redis()
    now = datetime.utcnow().isoformat()

    benchmark = {
        "id": benchmark_id,
        "product_type": product_type,
        "status": "pending",
        "config": config,
        "criteria": [],
        "created_at": now,
        "updated_at": now,
        "progress_message": "",
        "progress_percent": 0,
    }

    r.set(f"benchmark:{benchmark_id}", json.dumps(benchmark))
    r.set(f"benchmark:{benchmark_id}:products", json.dumps([]))

    # Ajouter à l'index (liste ordonnée, le plus récent en premier)
    r.lpush("benchmarks:index", benchmark_id)

    return {"id": benchmark_id, "product_type": product_type, "status": "pending"}


def update_benchmark_status(benchmark_id: str, status: str, message: str = "", percent: int = 0):
    """Met à jour le statut et la progression."""
    r = _get_redis()
    raw = r.get(f"benchmark:{benchmark_id}")
    if not raw:
        # Fallback : créer un benchmark minimal si inexistant
        print(f"[DB] WARNING: benchmark {benchmark_id} introuvable, création d'un stub")
        benchmark = {
            "id": benchmark_id,
            "product_type": "inconnu",
            "status": status,
            "config": {},
            "criteria": [],
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "progress_message": message,
            "progress_percent": percent,
        }
    else:
        benchmark = json.loads(raw)

    benchmark["status"] = status
    benchmark["progress_message"] = message
    benchmark["progress_percent"] = percent
    benchmark["updated_at"] = datetime.utcnow().isoformat()

    r.set(f"benchmark:{benchmark_id}", json.dumps(benchmark))


def update_benchmark_criteria(benchmark_id: str, criteria: list):
    """Enregistre les critères de comparaison."""
    r = _get_redis()
    raw = r.get(f"benchmark:{benchmark_id}")
    if not raw:
        return

    benchmark = json.loads(raw)
    benchmark["criteria"] = criteria
    benchmark["updated_at"] = datetime.utcnow().isoformat()

    r.set(f"benchmark:{benchmark_id}", json.dumps(benchmark))


# ─── PRODUITS ───


def save_product(benchmark_id: str, product: dict):
    """Ajoute ou met à jour un produit dans un benchmark."""
    r = _get_redis()

    # Charger la liste existante
    raw = r.get(f"benchmark:{benchmark_id}:products")
    products = json.loads(raw) if raw else []

    # Chercher si le produit existe déjà (par ID)
    product_id = product.get("id", "")
    found = False
    for i, p in enumerate(products):
        if p.get("id") == product_id:
            products[i] = product
            found = True
            break

    if not found:
        products.append(product)

    r.set(f"benchmark:{benchmark_id}:products", json.dumps(products))


# ─── LECTURE ───


def get_benchmark(benchmark_id: str) -> dict | None:
    """Récupère un benchmark complet avec ses produits."""
    r = _get_redis()

    raw = r.get(f"benchmark:{benchmark_id}")
    if not raw:
        return None

    benchmark = json.loads(raw)

    # Charger les produits
    raw_products = r.get(f"benchmark:{benchmark_id}:products")
    benchmark["products"] = json.loads(raw_products) if raw_products else []

    return benchmark


def list_benchmarks() -> list:
    """Liste tous les benchmarks (sans les produits)."""
    r = _get_redis()

    # Récupérer tous les IDs depuis l'index
    benchmark_ids = r.lrange("benchmarks:index", 0, -1)

    benchmarks = []
    for bid in benchmark_ids:
        raw = r.get(f"benchmark:{bid}")
        if raw:
            b = json.loads(raw)
            benchmarks.append({
                "id": b["id"],
                "product_type": b.get("product_type", ""),
                "status": b.get("status", ""),
                "progress_percent": b.get("progress_percent", 0),
                "created_at": b.get("created_at", ""),
            })

    return benchmarks
