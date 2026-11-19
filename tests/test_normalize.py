from linky_agents.normalize import canonical_url, clean_text, item_id, title_key


def test_canonical_url_strips_tracking_fragment_and_slash():
    url = "http://Example.com/news/post/?utm_source=x&b=2&a=1&fbclid=z#top"
    assert canonical_url(url) == "https://example.com/news/post?a=1&b=2"


def test_item_id_is_stable_across_tracking_variants():
    a = item_id("https://example.com/a?utm_medium=rss")
    b = item_id("https://example.com/a/")
    assert a == b
    assert len(a) == 16


def test_title_key_ignores_case_accents_and_punctuation():
    assert title_key("OpenAI lança GPT-6: o que muda?") == title_key(
        "openai lanca gpt 6 o que muda"
    )


def test_clean_text_removes_html_and_truncates_on_word_boundary():
    raw = "<p>Olá &amp; bem-vindo</p> " + "palavra " * 200
    out = clean_text(raw, limit=50)
    assert out.startswith("Olá & bem-vindo")
    assert out.endswith("…")
    assert len(out) <= 51


def test_clean_text_handles_none():
    assert clean_text(None) == ""
