"""
database.py — Gestion de la base de données PostgreSQL.
Stocke les benchmarks, produits et données collectées.
"""
import psycopg2
from psycopg2.extras import RealDictCursor
import json
import os

# On récupère l'URL de la base Postgres fournie par Railway
DATABASE_URL = os.getenv("DATABASE_URL")

def get_db():
    """Crée une connexion à la base de données PostgreSQL."""
    conn = psycopg2.connect(DATABASE_URL)
    return conn

def init_db():
    """Crée les tables si elles n'existent pas."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS benchmarks (
            id TEXT PRIMARY KEY,
            product_type TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            config TEXT DEFAULT '{}',
            criteria TEXT DEFAULT '[]',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
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
            collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completeness REAL DEFAULT 0.0,
            FOREIGN KEY (benchmark_id) REFERENCES benchmarks(id)
        );
    """)
    conn.commit()
    conn.close()

def create_benchmark(benchmark_id: str, product_type: str, config: dict) -> dict:
    conn = get_db()
    cursor = conn.cursor()
    # En PostgreSQL, on utilise %s au lieu de ? pour les variables
    cursor.execute(
        "INSERT INTO benchmarks (id, product_type, config) VALUES (%s, %s, %s)",
        (benchmark_id, product_type, json.dumps(config))
    )
    conn.commit()
    conn.close()
    return {"id": benchmark_id, "product_type": product_type, "status": "pending"}

def update_benchmark_status(benchmark_id: str, status: str, message: str = "", percent: int = 0):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        """UPDATE benchmarks 
           SET status = %s, progress_message = %s, progress_percent = %s, updated_at = CURRENT_TIMESTAMP
           WHERE id = %s""",
        (status, message, percent, benchmark_id)
    )
    conn.commit()
    conn.close()

def update_benchmark_criteria(benchmark_id: str, criteria: list):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE benchmarks SET criteria = %s WHERE id = %s",
        (json.dumps(criteria), benchmark_id)
    )
    conn.commit()
    conn.close()

def save_product(benchmark_id: str, product: dict):
    conn = get_db()
    cursor = conn.cursor()
    # Adaptation de "INSERT OR REPLACE" pour PostgreSQL
    cursor.execute(
        """INSERT INTO products 
           (id, benchmark_id, name, brand, image_url, source_url, price_min, price_max, data, completeness)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
           ON CONFLICT (id) DO UPDATE SET
           benchmark_id = EXCLUDED.benchmark_id,
           name = EXCLUDED.name,
           brand = EXCLUDED.brand,
           image_url = EXCLUDED.image_url,
           source_url = EXCLUDED.source_url,
           price_min = EXCLUDED.price_min,
           price_max = EXCLUDED.price_max,
           data = EXCLUDED.data,
           completeness = EXCLUDED.completeness,
           collected_at = CURRENT_TIMESTAMP""",
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
    conn = get_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT * FROM benchmarks WHERE id = %s", (benchmark_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return None

    benchmark = dict(row)
    # Conversion des dates en texte pour le JSON
    if benchmark.get("created_at"): benchmark["created_at"] = str(benchmark["created_at"])
    if benchmark.get("updated_at"): benchmark["updated_at"] = str(benchmark["updated_at"])
    benchmark["config"] = json.loads(benchmark["config"])
    benchmark["criteria"] = json.loads(benchmark["criteria"])

    cursor.execute(
        "SELECT * FROM products WHERE benchmark_id = %s ORDER BY brand, name",
        (benchmark_id,)
    )
    products = cursor.fetchall()
    benchmark["products"] = []
    for p in products:
        product = dict(p)
        if product.get("collected_at"): product["collected_at"] = str(product["collected_at"])
        product["data"] = json.loads(product["data"])
        benchmark["products"].append(product)

    conn.close()
    return benchmark

def list_benchmarks() -> list:
    conn = get_db()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute(
        "SELECT id, product_type, status, progress_percent, created_at FROM benchmarks ORDER BY created_at DESC"
    )
    rows = cursor.fetchall()
    conn.close()
    
    results = []
    for r in rows:
        d = dict(r)
        if d.get("created_at"): d["created_at"] = str(d["created_at"])
        results.append(d)
    return results