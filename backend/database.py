"""
database.py — Stockage Redis V6.
Ajout : candidats (phase sélection) et analyse de marché.
"""
import os
import json
import redis
from datetime import datetime

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
_redis_client = None


def _get_redis():
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    return _redis_client


def init_db():
    r = _get_redis()
    r.ping()
    print("[DB] Connexion Redis OK")


# ─── BENCHMARKS ───

def create_benchmark(benchmark_id: str, product_type: str, config: dict) -> dict:
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
    r.set(f"benchmark:{benchmark_id}:candidates", json.dumps([]))
    r.lpush("benchmarks:index", benchmark_id)
    return {"id": benchmark_id, "product_type": product_type, "status": "pending"}


def update_benchmark_status(benchmark_id: str, status: str, message: str = "", percent: int = 0):
    r = _get_redis()
    raw = r.get(f"benchmark:{benchmark_id}")
    if not raw:
        benchmark = {
            "id": benchmark_id, "product_type": "inconnu", "status": status,
            "config": {}, "criteria": [], "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "progress_message": message, "progress_percent": percent,
        }
    else:
        benchmark = json.loads(raw)
    benchmark["status"] = status
    benchmark["progress_message"] = message
    benchmark["progress_percent"] = percent
    benchmark["updated_at"] = datetime.utcnow().isoformat()
    r.set(f"benchmark:{benchmark_id}", json.dumps(benchmark))


def update_benchmark_criteria(benchmark_id: str, criteria: list):
    r = _get_redis()
    raw = r.get(f"benchmark:{benchmark_id}")
    if not raw:
        return
    benchmark = json.loads(raw)
    benchmark["criteria"] = criteria
    benchmark["updated_at"] = datetime.utcnow().isoformat()
    r.set(f"benchmark:{benchmark_id}", json.dumps(benchmark))


# ─── CANDIDATS (phase sélection) ───

def save_candidates(benchmark_id: str, candidates: list):
    r = _get_redis()
    r.set(f"benchmark:{benchmark_id}:candidates", json.dumps(candidates))


def get_candidates(benchmark_id: str) -> list:
    r = _get_redis()
    raw = r.get(f"benchmark:{benchmark_id}:candidates")
    return json.loads(raw) if raw else []


# ─── ANALYSE DE MARCHÉ ───

def save_market_research(benchmark_id: str, market_research: dict):
    r = _get_redis()
    r.set(f"benchmark:{benchmark_id}:market_research", json.dumps(market_research))


def get_market_research(benchmark_id: str) -> dict:
    r = _get_redis()
    raw = r.get(f"benchmark:{benchmark_id}:market_research")
    return json.loads(raw) if raw else {}


# ─── PRODUITS ───

def save_product(benchmark_id: str, product: dict):
    r = _get_redis()
    raw = r.get(f"benchmark:{benchmark_id}:products")
    products = json.loads(raw) if raw else []
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
    r = _get_redis()
    raw = r.get(f"benchmark:{benchmark_id}")
    if not raw:
        return None
    benchmark = json.loads(raw)
    raw_products = r.get(f"benchmark:{benchmark_id}:products")
    benchmark["products"] = json.loads(raw_products) if raw_products else []
    raw_candidates = r.get(f"benchmark:{benchmark_id}:candidates")
    benchmark["candidates"] = json.loads(raw_candidates) if raw_candidates else []
    return benchmark


def list_benchmarks() -> list:
    r = _get_redis()
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
