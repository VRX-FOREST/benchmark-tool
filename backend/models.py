"""
models.py — Modèles de données Pydantic.
Définit la structure des requêtes et réponses de l'API.
"""
from pydantic import BaseModel
from typing import Optional


class BenchmarkRequest(BaseModel):
    """Ce que l'utilisateur envoie pour lancer un benchmark."""
    product_type: str  # Ex: "casques audio à réduction de bruit"
    price_min: Optional[float] = None
    price_max: Optional[float] = None
    market: str = "France"  # France, Europe, mondial
    segment: str = "tous"  # entrée de gamme, milieu, premium, tous
    max_products: int = 10


class BenchmarkStatus(BaseModel):
    """Statut d'un benchmark en cours."""
    id: str
    product_type: str
    status: str  # pending, selecting, collecting, normalizing, done, error
    progress_message: str = ""
    progress_percent: int = 0


class ProductData(BaseModel):
    """Données d'un produit collecté."""
    id: str
    name: str
    brand: str = ""
    image_url: str = ""
    source_url: str = ""
    price_min: Optional[float] = None
    price_max: Optional[float] = None
    data: dict = {}
    completeness: float = 0.0