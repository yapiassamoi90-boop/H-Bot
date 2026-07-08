FROM python:3.10-slim

# Installer tesseract
RUN apt-get update && apt-get install -y tesseract-ocr tesseract-ocr-fra && rm -rf /var/lib/apt/lists/*

# Dossier de travail
WORKDIR /app

# Copier les fichiers
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Lancer le bot
CMD ["python", "hbot.py"]
