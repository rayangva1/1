# Image de l'API interne du moteur — {{NOM_BOUTIQUE}} (agent integrations, SPEC §1 et §2.7).
#
# Construire (plus tard, sur décision) :  docker build -t pokeshop-api .
# Lancer : via docker-compose.yml (voir ce fichier). Aucun secret dans l'image : jetons, URL de
# base et mots de passe arrivent par variables d'environnement depuis le coffre (.env local non
# versionné). Simulation par défaut : POKESHOP_DRY_RUN=true.
#
# Versions épinglées = versions avec lesquelles la suite de tests est verte le 4.10.2026.
# psycopg (hors liste SPEC §1) : pilote PostgreSQL des adaptateurs audit, idempotence, incidents
# et autonomie (SQL paramétré, aucun ORM) ; sans POKESHOP_DATABASE_URL, il n'est pas utilisé.

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app/engine \
    POKESHOP_DRY_RUN=true \
    TZ=Europe/Zurich

WORKDIR /app

RUN pip install \
        "pydantic==2.13.4" \
        "fastapi==0.142.2" \
        "uvicorn==0.50.2" \
        "httpx==0.28.1" \
        "openpyxl==3.1.5" \
        "PyYAML==6.0.1" \
        "Jinja2==3.1.6" \
        "psycopg[binary]==3.3.6"

COPY engine/ engine/
COPY config/ config/
COPY data/ data/

RUN useradd --create-home --uid 10001 pokeshop \
    && mkdir -p /app/state \
    && chown pokeshop:pokeshop /app/state

USER pokeshop

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status == 200 else 1)"

CMD ["uvicorn", "pokeshop.api:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
