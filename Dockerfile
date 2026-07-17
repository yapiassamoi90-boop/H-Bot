# Utilisation d'une image légère
FROM python:3.10-slim

# Empêche Python d'écrire des fichiers .pyc et permet aux logs de s'afficher en temps réel
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# 1. Installer Tesseract et ses dépendances en 1 seule commande + nettoyer le cache
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-fra \
    libgl1 \
    && rm -rf /var/lib/apt/lists/*

# 2. Copier requirements d'abord pour profiter du cache Docker
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 3. Copier tout le contenu du projet dans le dossier /app
COPY . .

# 4. Lancer l'application
CMD ["python", "main.py"]
