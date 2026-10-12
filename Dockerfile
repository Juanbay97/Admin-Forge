# Prometheon Forge control plane image: admin SPA + Python wheel, non-root, no secrets.
#
#   docker build -t forge-control-plane:local .
#
# Every base image is pinned by digest (refresh with `docker buildx imagetools inspect <tag>`).
# Nothing secret is an ARG or ENV: credentials arrive at run time as Docker secrets (`*_FILE`).

# --- 1. Admin SPA: Vite writes ../src/forge/web/admin (gitignored), which the wheel packages.
FROM node:22-alpine@sha256:0a7108bf6c7bf5de370ffb1a3ed6be93d405b43ff159f681a8d18c0e2bc2e402 AS admin
WORKDIR /build/admin
COPY admin/package.json admin/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY admin/ ./
RUN npm run build

# --- 2. Python package + pinned dependencies, installed into an isolated prefix.
FROM python:3.12-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f AS wheel
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /build
COPY pyproject.toml ./
COPY src/ ./src/
COPY --from=admin /build/src/forge/web/admin ./src/forge/web/admin
RUN pip install --prefix=/install .

# --- 3. Runtime: no build tools, no pip cache, unprivileged user, read-only friendly.
FROM python:3.12-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN groupadd --system --gid 10001 forge \
    && useradd --system --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin forge
COPY --from=wheel /install /usr/local
COPY migrations/ /app/migrations/
WORKDIR /app
USER 10001:10001
ENTRYPOINT ["python", "-m", "forge.serve_prod"]
CMD ["serve"]
