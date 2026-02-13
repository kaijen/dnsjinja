# ---- Base stage ----
FROM python:3.12-slim AS base
WORKDIR /app
COPY . .

# ---- Production ----
FROM base AS prod
RUN pip install --no-cache-dir .
WORKDIR /data
ENTRYPOINT ["dnsjinja"]

# ---- Development ----
FROM base AS dev
RUN pip install --no-cache-dir -e .
WORKDIR /data
ENTRYPOINT ["dnsjinja"]
