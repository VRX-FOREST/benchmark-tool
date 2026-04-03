"""
celery_app.py — Configuration de Celery.
Celery gère l'exécution des tâches longues (collecte de données)
en arrière-plan, pendant que l'utilisateur voit la progression.
"""
import os
from celery import Celery

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery = Celery(
    "benchmark",
    broker=REDIS_URL,
    backend=REDIS_URL,
)

celery.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Europe/Paris",
    enable_utc=True,
    # Timeout élevé car la collecte peut prendre plusieurs minutes
    task_soft_time_limit=600,  # 10 minutes
    task_time_limit=900,  # 15 minutes max
    # Éviter la ré-exécution des tâches longues
    broker_transport_options={"visibility_timeout": 3600},
)
