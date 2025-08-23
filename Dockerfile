# Dockerfile (racine du repo)
FROM python:3.12-slim

# 1) Libs système requises par Chromium/Playwright
RUN apt-get update && apt-get install -y --no-install-recommends \
  libglib2.0-0 libnspr4 libnss3 libdbus-1-3 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
  libxcb1 libxkbcommon0 libatspi2.0-0 libx11-6 libxcomposite1 libxdamage1 libxext6 \
  libxfixes3 libxrandr2 libgbm1 libcairo2 libpango-1.0-0 libasound2 \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 2) Dépendances Python (pinne Playwright pour éviter les écarts de build)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 3) Télécharge le binaire Chromium pour Playwright dans un chemin stable
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN python -m playwright install chromium

# 4) Copie le code
COPY . .

# 5) Démarre l’API
CMD ["uvicorn","backend.main:app","--host","0.0.0.0","--port","8080","--workers","1","--timeout-keep-alive","65"]