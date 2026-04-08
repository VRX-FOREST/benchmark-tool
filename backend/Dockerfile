FROM python:3.12-slim

# 1. Variables d'environnement pour Python et Playwright
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

# 2. Dépendances système
RUN apt-get update && apt-get install -y \
    wget \
    && rm -rf /var/lib/apt/lists/*

# 3. Installation des dépendances Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. Installation de Playwright (Chromium uniquement)
RUN playwright install --with-deps chromium

# 5. SÉCURITÉ : Créer un utilisateur non-root (Règle le Warning Celery)
RUN useradd -m scraperuser
# Donner les droits sur le dossier app et les navigateurs
RUN chown -R scraperuser:scraperuser /app /ms-playwright
USER scraperuser

# 6. Copier le reste du code
COPY --chown=scraperuser:scraperuser . .

EXPOSE 8000

# Par défaut lance FastAPI, mais permet d'être surchargé par Railway pour le worker
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]