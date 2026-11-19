"""Coletor determinístico de notícias (sem LLM).

Uso:
    linky-collect --sources sources/sources.yaml --data data

Cada execução:
- busca os feeds em paralelo, com GET condicional (ETag/Last-Modified);
- normaliza, filtra por palavras-chave (fontes generalistas) e por janela de 3 dias;
- grava itens novos em data/items/AAAA-MM-DD.jsonl, pela data de publicação no fuso de Brasília,
  sem duplicar (mesma URL canônica ou mesmo título no dia);
- grava estatísticas por fonte em data/runs/<timestamp>.json.

Pode rodar várias vezes ao dia: cada execução só acrescenta o que é novo.
"""

from __future__ import annotations

import argparse
import calendar
import json
import logging
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from zoneinfo import ZoneInfo

import feedparser
import httpx

from linky_agents import __version__
from linky_agents.normalize import canonical_url, clean_text, item_id, title_key
from linky_agents.sources import KeywordMatcher, Source, SourcesConfig, load_sources

BRT = ZoneInfo("America/Sao_Paulo")
USER_AGENT = f"linky-dev-collector/{__version__} (personal news curation; RSS reader)"
WINDOW_DAYS = 3
log = logging.getLogger("linky.collect")


@dataclass
class SourceStats:
    source: str
    http_status: int | str = "-"
    not_modified: bool = False
    entries: int = 0
    kept: int = 0
    filtered_keyword: int = 0
    filtered_old: int = 0
    no_date: int = 0
    duplicates: int = 0
    error: str | None = None
    elapsed_ms: int = 0


@dataclass
class FetchResult:
    source: Source
    stats: SourceStats
    entries: list = field(default_factory=list)
    etag: str | None = None
    last_modified: str | None = None
    base_url: str | None = None  # link do site no feed, para resolver links relativos


def _fetch(client: httpx.Client, source: Source, cache: dict) -> FetchResult:
    stats = SourceStats(source=source.id)
    headers = {}
    cached = cache.get(source.id, {})
    if cached.get("etag"):
        headers["If-None-Match"] = cached["etag"]
    if cached.get("last_modified"):
        headers["If-Modified-Since"] = cached["last_modified"]
    started = time.monotonic()
    result = FetchResult(source=source, stats=stats)
    for attempt in (1, 2):
        try:
            resp = client.get(str(source.url), headers=headers)
            stats.http_status = resp.status_code
            if resp.status_code == 304:
                stats.not_modified = True
                break
            resp.raise_for_status()
            parsed = feedparser.parse(resp.content)
            result.entries = list(parsed.entries)
            result.base_url = parsed.feed.get("link") or str(source.url)
            result.etag = resp.headers.get("etag")
            result.last_modified = resp.headers.get("last-modified")
            stats.entries = len(result.entries)
            stats.error = None
            break
        except Exception as exc:  # noqa: BLE001 - registrar qualquer falha por fonte
            stats.error = f"{type(exc).__name__}: {exc}"[:200]
            if attempt == 1:
                time.sleep(2)
    stats.elapsed_ms = int((time.monotonic() - started) * 1000)
    return result


def _published_utc(entry) -> datetime | None:
    struct = entry.get("published_parsed") or entry.get("updated_parsed")
    if not struct:
        return None
    return datetime.fromtimestamp(calendar.timegm(struct), tz=UTC)


def _absolute_link(link: str | None, base: str) -> str | None:
    """Resolve links relativos (ex.: HBR publica "/2026/11/...") contra o site do feed."""
    if not link:
        return None
    resolved = urljoin(base, link.strip())
    parts = urlsplit(resolved)
    return resolved if parts.scheme in ("http", "https") and parts.netloc else None


def _load_day_index(path: Path) -> tuple[set[str], set[str]]:
    ids: set[str] = set()
    titles: set[str] = set()
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rec = json.loads(line)
                ids.add(rec["id"])
                titles.add(rec["title_key"])
    return ids, titles


def process(
    results: list[FetchResult],
    config: SourcesConfig,
    data_dir: Path,
    now: datetime,
) -> dict[str, int]:
    """Filtra, deduplica e grava. Retorna contagem de itens novos por dia (BRT)."""
    matcher = KeywordMatcher(config.keywords)
    cutoff = now - timedelta(days=WINDOW_DAYS)
    items_dir = data_dir / "items"
    items_dir.mkdir(parents=True, exist_ok=True)
    indexes: dict[str, tuple[set[str], set[str]]] = {}
    new_by_day: dict[str, int] = {}
    limit = config.defaults.max_items_per_run

    for res in results:
        for entry in res.entries[:limit]:
            title = clean_text(entry.get("title"), limit=300)
            link = _absolute_link(entry.get("link"), res.base_url or str(res.source.url))
            if not title or not link:
                continue
            published = _published_utc(entry)
            if published is None:
                res.stats.no_date += 1
                continue
            if published < cutoff:
                res.stats.filtered_old += 1
                continue
            summary = clean_text(entry.get("summary") or entry.get("description"))
            if res.source.filter and not matcher.matches(f"{title} {summary}"):
                res.stats.filtered_keyword += 1
                continue

            day = published.astimezone(BRT).date().isoformat()
            if day not in indexes:
                indexes[day] = _load_day_index(items_dir / f"{day}.jsonl")
            ids, titles = indexes[day]
            iid, tkey = item_id(link), title_key(title)
            if iid in ids or tkey in titles:
                res.stats.duplicates += 1
                continue

            record = {
                "id": iid,
                "source": res.source.id,
                "tier": res.source.tier,
                "title": title,
                "title_key": tkey,
                "url": canonical_url(link),
                "summary": summary,
                "published_utc": published.isoformat(),
                "published_brt_date": day,
                "collected_utc": now.isoformat(),
            }
            with (items_dir / f"{day}.jsonl").open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
            ids.add(iid)
            titles.add(tkey)
            res.stats.kept += 1
            new_by_day[day] = new_by_day.get(day, 0) + 1
    return new_by_day


def run(sources_path: Path, data_dir: Path, workers: int = 8) -> int:
    config = load_sources(sources_path)
    state_path = data_dir / "state" / "http_cache.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    cache = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    now = datetime.now(tz=UTC)

    with (
        httpx.Client(
            headers={"User-Agent": USER_AGENT},
            timeout=httpx.Timeout(20.0),
            follow_redirects=True,
        ) as client,
        ThreadPoolExecutor(max_workers=workers) as pool,
    ):
        results = list(pool.map(lambda s: _fetch(client, s, cache), config.enabled()))

    new_by_day = process(results, config, data_dir, now)

    for res in results:
        if res.etag or res.last_modified:
            cache[res.source.id] = {"etag": res.etag, "last_modified": res.last_modified}
    state_path.write_text(json.dumps(cache, indent=2), encoding="utf-8")

    runs_dir = data_dir / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "run_utc": now.isoformat(),
        "version": __version__,
        "new_items_by_day": new_by_day,
        "sources": [asdict(r.stats) for r in results],
    }
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    (runs_dir / f"{stamp}.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    failed = [r.stats.source for r in results if r.stats.error]
    log.info("novos itens: %s | fontes com erro: %s", new_by_day, failed or "nenhuma")
    return 1 if failed and len(failed) == len(results) else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Coletor determinístico do linky-dev")
    parser.add_argument("--sources", type=Path, default=Path("sources/sources.yaml"))
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    return run(args.sources, args.data, args.workers)


if __name__ == "__main__":
    sys.exit(main())
