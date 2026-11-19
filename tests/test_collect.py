import json
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from linky_agents.collect import FetchResult, SourceStats, process
from linky_agents.sources import KeywordMatcher, Keywords, Source, SourcesConfig, load_sources

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 11, 6, 7, 0, tzinfo=UTC)  # 04:00 em Brasília


def _entry(title, link, published: datetime, summary=""):
    return {
        "title": title,
        "link": link,
        "summary": summary,
        "published_parsed": time.gmtime(published.timestamp()),
    }


def _config(filter_source: bool = False) -> SourcesConfig:
    return SourcesConfig(
        keywords=Keywords(
            case_insensitive=[r"intelig[eê]ncia artificial"], case_sensitive=[r"\bIA\b"]
        ),
        sources=[
            Source(
                id="s1", name="S1", url="https://s1.test/feed", tier="press", filter=filter_source
            )
        ],
    )


def _result(config: SourcesConfig, entries) -> FetchResult:
    src = config.sources[0]
    return FetchResult(source=src, stats=SourceStats(source=src.id), entries=entries)


def _read(day_file: Path) -> list[dict]:
    return [json.loads(x) for x in day_file.read_text(encoding="utf-8").splitlines()]


def test_real_sources_file_is_valid():
    config = load_sources(ROOT / "sources" / "sources.yaml")
    assert len(config.enabled()) >= 20
    assert {s.tier for s in config.sources} == {"primary", "press", "analysis", "br"}


def test_keyword_matcher_acronym_is_case_sensitive():
    m = KeywordMatcher(Keywords(case_sensitive=[r"\bIA\b"]))
    assert m.matches("Empresa adota IA no atendimento")
    assert not m.matches("A ia e volta")  # 'ia' minúsculo é verbo, não sigla


def test_items_grouped_by_brt_date_and_deduplicated(tmp_path):
    config = _config()
    late_night_utc = datetime(2026, 11, 6, 1, 30, tzinfo=UTC)  # 22:30 de 05/11 em Brasília
    entries = [
        _entry("Notícia A", "https://x.test/a?utm_source=rss", late_night_utc),
        _entry("Notícia A", "https://x.test/a", late_night_utc),  # mesma URL canônica
        _entry("notícia a!", "https://y.test/outra-url", late_night_utc),  # mesmo título
    ]
    res = _result(config, entries)
    new = process([res], config, tmp_path, NOW)
    assert new == {"2026-11-05": 1}
    assert res.stats.kept == 1 and res.stats.duplicates == 2
    rec = _read(tmp_path / "items" / "2026-11-05.jsonl")[0]
    assert rec["url"] == "https://x.test/a"


def test_second_run_adds_nothing_new(tmp_path):
    config = _config()
    entries = [_entry("Notícia B", "https://x.test/b", NOW - timedelta(hours=3))]
    process([_result(config, entries)], config, tmp_path, NOW)
    second = _result(config, entries)
    assert process([second], config, tmp_path, NOW) == {}
    assert second.stats.duplicates == 1


def test_old_and_off_topic_items_are_filtered(tmp_path):
    config = _config(filter_source=True)
    entries = [
        _entry("Inteligência artificial no varejo", "https://x.test/ok", NOW - timedelta(hours=5)),
        _entry("Receita de bolo", "https://x.test/bolo", NOW - timedelta(hours=5)),
        _entry("IA antiga", "https://x.test/velha", NOW - timedelta(days=10)),
    ]
    res = _result(config, entries)
    process([res], config, tmp_path, NOW)
    assert res.stats.kept == 1
    assert res.stats.filtered_keyword == 1
    assert res.stats.filtered_old == 1


def test_entries_without_date_are_skipped(tmp_path):
    config = _config()
    res = _result(config, [{"title": "Sem data", "link": "https://x.test/nd"}])
    process([res], config, tmp_path, NOW)
    assert res.stats.no_date == 1 and res.stats.kept == 0


def test_relative_links_resolved_against_feed_site(tmp_path):
    config = _config()
    res = _result(config, [_entry("Artigo sobre IA", "/2026/11/artigo", NOW - timedelta(hours=2))])
    res.base_url = "https://hbr.org"
    process([res], config, tmp_path, NOW)
    (rec,) = _read(tmp_path / "items" / "2026-11-06.jsonl")
    assert rec["url"] == "https://hbr.org/2026/11/artigo"
