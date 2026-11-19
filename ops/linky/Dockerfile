# Serviço HTTP do harness (linky-agents). Build a partir da raiz do repositório:
#   docker build -f ops/linky/Dockerfile -t linky-agents:latest .
# Dois estágios: o uv só existe no build; a imagem final leva o Python e o .venv.

FROM python:3.12-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.12.9 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
# Dependências primeiro: a camada só muda quando o lockfile muda
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
COPY config ./config
COPY prompts ./prompts
# Motor de composição (ADR 0006): tokens da marca e fontes, lidos pelo render sem fontes do sistema
COPY assets ./assets
RUN uv sync --frozen --no-dev

FROM python:3.12-slim
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin linky \
 && mkdir /data && chown linky:linky /data
COPY --from=build /app /app
WORKDIR /app
ENV PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    LINKY_DATA_DIR=/data \
    LINKY_ASSETS=/app/assets \
    LINKY_PORT=8080
USER linky
VOLUME /data
EXPOSE 8080
# Na partida, checa a cada 2 s (o deploy espera o "healthy"); depois, a cada minuto
HEALTHCHECK --interval=60s --timeout=5s --start-period=30s --start-interval=2s --retries=3 \
  CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/health' % os.environ.get('LINKY_PORT', '8080'), timeout=4)"]
CMD ["python", "-m", "linky_agents.service"]
