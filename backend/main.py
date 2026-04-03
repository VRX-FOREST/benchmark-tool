"""
main.py — Serveur FastAPI.
Point d'entrée de l'application backend.
Expose les endpoints API que le frontend appelle.
"""
import os
import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

load_dotenv()

from database import init_db, create_benchmark, get_benchmark, list_benchmarks, update_benchmark_status
from models import BenchmarkRequest, BenchmarkStatus
from tasks import run_benchmark


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise la base de données au démarrage."""
    init_db()
    yield

app = FastAPI(
    title="Benchmark Produits",
    description="Outil de benchmark intelligent de produits physiques",
    version="1.0.0",
    lifespan=lifespan,
)

# Autoriser les requêtes cross-origin (le frontend est sur un port différent)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En production, restreindre au domaine du frontend
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Endpoints API ───


@app.get("/api/health")
async def health():
    """Vérifie que le serveur fonctionne."""
    return {"status": "ok", "version": "1.0.0"}


@app.post("/api/benchmarks")
async def create_new_benchmark(request: BenchmarkRequest):
    """
    Lance un nouveau benchmark.
    Crée l'entrée en base et démarre la tâche Celery en arrière-plan.
    """
    benchmark_id = str(uuid.uuid4())

    config = {
        "price_min": request.price_min,
        "price_max": request.price_max,
        "market": request.market,
        "segment": request.segment,
        "max_products": request.max_products,
    }

    # Créer l'entrée en base
    create_benchmark(benchmark_id, request.product_type, config)

    # Lancer la collecte en arrière-plan via Celery
    run_benchmark.delay(benchmark_id, request.product_type, config)

    return {
        "id": benchmark_id,
        "product_type": request.product_type,
        "status": "pending",
        "message": "Benchmark lancé ! La collecte est en cours.",
    }


@app.get("/api/benchmarks")
async def get_all_benchmarks():
    """Liste tous les benchmarks."""
    return list_benchmarks()


@app.get("/api/benchmarks/{benchmark_id}")
async def get_benchmark_detail(benchmark_id: str):
    """
    Récupère le détail d'un benchmark : statut, progression, produits collectés.
    Le frontend appelle cet endpoint en boucle pour suivre la progression.
    """
    benchmark = get_benchmark(benchmark_id)
    if not benchmark:
        raise HTTPException(status_code=404, detail="Benchmark non trouvé")
    return benchmark


@app.get("/api/benchmarks/{benchmark_id}/status")
async def get_benchmark_status(benchmark_id: str):
    """Endpoint léger pour récupérer uniquement le statut (polling rapide)."""
    benchmark = get_benchmark(benchmark_id)
    if not benchmark:
        raise HTTPException(status_code=404, detail="Benchmark non trouvé")
    return {
        "id": benchmark["id"],
        "status": benchmark["status"],
        "progress_message": benchmark["progress_message"],
        "progress_percent": benchmark["progress_percent"],
    }


# ─── Servir le frontend (en production) ───

if os.path.exists("static"):
    app.mount("/", StaticFiles(directory="static", html=True), name="frontend")
