# SanVi Budget Watch: the first image SanVi builds itself.
# Built, scanned (Trivy), given an SBOM (Syft) and signed (cosign keyless) by
# .github/workflows/secure-pipeline.yml. Kyverno only admits it if the signature verifies.
FROM python:3.12-alpine

# Pull in security fixes for the base OS at build time
RUN apk upgrade --no-cache

WORKDIR /app
COPY scripts/budget_watch.py /app/budget_watch.py

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Never run as root: 65534 is the standard "nobody" user
USER 65534:65534

ENTRYPOINT ["python3", "/app/budget_watch.py"]
