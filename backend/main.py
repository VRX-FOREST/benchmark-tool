"""
main.py — Serveur FastAPI V6.
Nouveau flow :
  POST /api/benchmarks/discover   → Phase 1 : découverte des produits candidats
  POST /api/benchmarks/launch     → Phase 2 : lancement du benchmark sur les produits sélectionnés
  GET  /api/benchmarks            → Liste des benchmarks
  GET  /api/benchmarks/{id}       → Détail d'un benchmark
"""
import os
import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

from database import init_db, create_benchmark, get_benchmark, list_benchmarks
from tasks import run_benchmark, discover_products_task


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(
    title="Benchmark Produits",
    description="Outil de benchmark intelligent de produits physiques",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Modèles ───

class DiscoverRequest(BaseModel):
    product_type: str
    price_min: Optional[float] = None
    price_max: Optional[float] = None
    market: str = "France"
    segment: str = "tous"
    max_products: int = 12

class LaunchRequest(BaseModel):
    benchmark_id: str
    selected_products: list[dict]  # Liste des produits sélectionnés par l'utilisateur

class BenchmarkRequest(BaseModel):
    product_type: str
    price_min: Optional[float] = None
    price_max: Optional[float] = None
    market: str = "France"
    segment: str = "tous"
    max_products: int = 10


# ─── Endpoints ───

@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "2.0.0"}


@app.post("/api/benchmarks/discover")
async def discover_products(request: DiscoverRequest):
    """
    Phase 1 : Découverte des produits candidats.
    L'agent cherche les produits, leur prix, photo et lien.
    L'utilisateur sélectionnera ensuite ceux qu'il veut benchmarker.
    """
    benchmark_id = str(uuid.uuid4())
    config = {
        "price_min": request.price_min,
        "price_max": request.price_max,
        "market": request.market,
        "segment": request.segment,
        "max_products": request.max_products,
    }

    create_benchmark(benchmark_id, request.product_type, config)

    # Lancer la découverte en arrière-plan
    discover_products_task.delay(benchmark_id, request.product_type, config)

    return {
        "id": benchmark_id,
        "product_type": request.product_type,
        "status": "discovering",
        "message": "Recherche des produits candidats en cours...",
    }


@app.post("/api/benchmarks/launch")
async def launch_benchmark(request: LaunchRequest):
    """
    Phase 2 : Lance le benchmark complet sur les produits sélectionnés.
    """
    benchmark = get_benchmark(request.benchmark_id)
    if not benchmark:
        raise HTTPException(status_code=404, detail="Benchmark non trouvé")

    # Lancer la deep research sur les produits sélectionnés
    run_benchmark.delay(
        request.benchmark_id,
        benchmark["product_type"],
        benchmark["config"],
        request.selected_products,
    )

    return {
        "id": request.benchmark_id,
        "status": "collecting",
        "message": f"Deep research lancée sur {len(request.selected_products)} produits.",
    }


@app.post("/api/benchmarks")
async def create_new_benchmark(request: BenchmarkRequest):
    """Legacy endpoint — lance directement sans étape de sélection."""
    benchmark_id = str(uuid.uuid4())
    config = {
        "price_min": request.price_min,
        "price_max": request.price_max,
        "market": request.market,
        "segment": request.segment,
        "max_products": request.max_products,
    }
    create_benchmark(benchmark_id, request.product_type, config)
    run_benchmark.delay(benchmark_id, request.product_type, config, None)
    return {"id": benchmark_id, "status": "pending", "message": "Benchmark lancé."}


@app.get("/api/benchmarks")
async def get_all_benchmarks():
    return list_benchmarks()


@app.get("/api/benchmarks/{benchmark_id}")
async def get_benchmark_detail(benchmark_id: str):
    benchmark = get_benchmark(benchmark_id)
    if not benchmark:
        raise HTTPException(status_code=404, detail="Benchmark non trouvé")
    return benchmark


@app.get("/api/benchmarks/{benchmark_id}/status")
async def get_benchmark_status(benchmark_id: str):
    benchmark = get_benchmark(benchmark_id)
    if not benchmark:
        raise HTTPException(status_code=404, detail="Benchmark non trouvé")
    return {
        "id": benchmark["id"],
        "status": benchmark["status"],
        "progress_message": benchmark["progress_message"],
        "progress_percent": benchmark["progress_percent"],
    }


if os.path.exists("static"):
    app.mount("/", StaticFiles(directory="static", html=True), name="frontend")
