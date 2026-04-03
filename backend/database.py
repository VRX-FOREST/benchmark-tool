"""
database.py — Gestion de la base de données SQLite.
Stocke les benchmarks, produits et données collectées.
"""
import sqlite3
import json
import os
from datetime import datetime

DB_PATH = os.getenv("DB_PATH", "benchmarks.db")


def get_db():
    """Crée une connexion à la base de données."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Crée les tables si elles n'existent pas."""
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS benchmarks (
            id TEXT PRIMARY KEY,
            product_type TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            config TEXT DEFAULT '{}',
            criteria TEXT DEFAULT '[]',
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            progress_message TEXT DEFAULT '',
            progress_percent INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS products (
            id TEXT PRIMARY KEY,
            benchmark_id TEXT NOT NULL,
            name TEXT NOT NULL,
            brand TEXT DEFAULT '',
            image_url TEXT DEFAULT '',
            source_url TEXT DEFAULT '',
            price_min REAL,
            price_max REAL,
            data TEXT DEFAULT '{}',
            collected_at TEXT DEFAULT (datetime('now')),
            completeness REAL DEFAULT 0.0,
            FOREIGN KEY (benchmark_id) REFERENCES benchmarks(id)
        );
    """)
    conn.commit()
    conn.close()


def create_benchmark(benchmark_id: str, product_type: str, config: dict) -> dict:
    """Crée un nouveau benchmark dans la base."""
    conn = get_db()
    conn.execute(
        "INSERT INTO benchmarks (id, product_type, config) VALUES (?, ?, ?)",
        (benchmark_id, product_type, json.dumps(config))
    )
    conn.commit()
    conn.close()
    return {"id": benchmark_id, "product_type": product_type, "status": "pending"}


def update_benchmark_status(benchmark_id: str, status: str, message: str = "", percent: int = 0):
    """Met à jour le statut et la progression d'un benchmark."""
    conn = get_db()
    conn.execute(
        """UPDATE benchmarks 
           SET status = ?, progress_message = ?, progress_percent = ?, updated_at = datetime('now')
           WHERE id = ?""",
        (status, message, percent, benchmark_id)
    )
    conn.commit()
    conn.close()


def update_benchmark_criteria(benchmark_id: str, criteria: list):
    """Enregistre les critères de comparaison."""
    conn = get_db()
    conn.execute(
        "UPDATE benchmarks SET criteria = ? WHERE id = ?",
        (json.dumps(criteria), benchmark_id)
    )
    conn.commit()
    conn.close()


def save_product(benchmark_id: str, product: dict):
    """Enregistre ou met à jour un produit collecté."""
    conn = get_db()
    conn.execute(
        """INSERT OR REPLACE INTO products 
           (id, benchmark_id, name, brand, image_url, source_url, price_min, price_max, data, completeness)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            product["id"],
            benchmark_id,
            product.get("name", ""),
            product.get("brand", ""),
            product.get("image_url", ""),
            product.get("source_url", ""),
            product.get("price_min"),
            product.get("price_max"),
            json.dumps(product.get("data", {})),
            product.get("completeness", 0.0),
        )
    )
    conn.commit()
    conn.close()


def get_benchmark(benchmark_id: str) -> dict | None:
    """Récupère un benchmark et tous ses produits."""
    conn = get_db()
    row = conn.execute("SELECT * FROM benchmarks WHERE id = ?", (benchmark_id,)).fetchone()
    if not row:
        conn.close()
        return None

    benchmark = dict(row)
    benchmark["config"] = json.loads(benchmark["config"])
    benchmark["criteria"] = json.loads(benchmark["criteria"])

    products = conn.execute(
        "SELECT * FROM products WHERE benchmark_id = ? ORDER BY brand, name",
        (benchmark_id,)
    ).fetchall()
    benchmark["products"] = []
    for p in products:
        product = dict(p)
        product["data"] = json.loads(product["data"])
        benchmark["products"].append(product)

    conn.close()
    return benchmark


def list_benchmarks() -> list:
    """Liste tous les benchmarks (sans les produits)."""
    conn = get_db()
    rows = conn.execute(
        "SELECT id, product_type, status, progress_percent, created_at FROM benchmarks ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
