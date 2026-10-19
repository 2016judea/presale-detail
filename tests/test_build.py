"""python3 -m pytest -q tests/   (no network, no model: pure page assembly)."""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import build  # noqa: E402

TPL = (Path(__file__).resolve().parent.parent / "scripts" / "page.html").read_text()


def test_a_listing_title_cannot_break_out_of_the_data_script():
    """Titles, locations and findings are scraped text. json.dumps leaves "</" alone, so a
    seller who typed </script> into a Craigslist title closed the page's data block and
    ran whatever followed."""
    evil = '</script><img src=x onerror="alert(1)">'
    data = {"meta": {"city": "minneapolis", "fetched_at": "2026-10-18T12:00:00+00:00", "counts": {}, "prices": []},
            "cards": [{"id": "1", "title": evil, "findings": ["dirty   line"]}]}
    page = build.render_page(TPL, data, "minneapolis")
    scripts = re.findall(r"<script[^>]*>(.*?)</script>", page, re.S)
    data_block = next(s for s in scripts if "const DATA=" in s)
    assert "</script" not in data_block
    assert "onerror" in data_block  # the text is still carried, just not as markup
    # and the browser reads back exactly what was embedded
    embedded = re.search(r"const DATA=(.*?);\nconst \$=", data_block, re.S).group(1)
    assert json.loads(embedded) == data
    assert " " not in embedded


def test_embed_json_escapes_only_what_breaks_a_script():
    assert build.embed_json({"t": "</script>"}) == '{"t": "<\\/script>"}'
    assert build.embed_json({"t": "a/b"}) == '{"t": "a/b"}'
