# ---- Step 2: containerise ----------------------------------------------------------------------
# A Dockerfile is a recipe for an IMAGE (a frozen, runnable snapshot of your app + its dependencies).
# Running an image gives a CONTAINER (an isolated process). Every instruction below creates a cached "layer".

# 1. Start from an official, small Python image. 3.12-slim = Debian + Python 3.12 without extras.
FROM python:3.12-slim

# 2. Sensible Python defaults for containers: no .pyc files, unbuffered logs (so you see them immediately).
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8080

WORKDIR /srv

# 3. Install dependencies FIRST and copy the code AFTER. Docker caches layers: as long as requirements.txt is unchanged,
#    code edits rebuild in seconds because this expensive layer is reused. (Order matters!)
COPY requirements.txt .
RUN pip install -r requirements.txt

# 4. Copy only what the service needs (see .dockerignore for what is excluded: notebooks, tests, virtualenvs...).
COPY app ./app
COPY artifacts ./artifacts

# 5. Security: do not run as root. If the app were ever compromised, the attacker gets an unprivileged user.
RUN useradd --create-home --uid 10001 appuser
USER appuser

# 6. EXPOSE documents the port; it does not publish it (that is `docker run -p`). Cloud Run injects its own PORT variable.
EXPOSE 8080

# 7. Container health check: the platform can restart the container if /health stops answering.
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/health' % os.getenv('PORT','8080'))" || exit 1

# 8. The command that starts the service. `exec` makes uvicorn PID 1 so it receives shutdown signals properly.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
