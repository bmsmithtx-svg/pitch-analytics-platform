"""Offline publishing-boundary and navigation checks; JS behavior uses Node."""
from html.parser import HTMLParser
from pathlib import Path
import tomllib

ROOT = Path(__file__).resolve().parents[1]


class Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.elements = []

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))


def test_publishing_boundary_and_navigation():
    docs = ROOT / "docs"
    assert {p.name for p in docs.iterdir()} == {
        "index.html", "styles.css", "config.js", "launch.js", ".nojekyll",
    }
    assert not any(p.is_symlink() for p in docs.iterdir())
    page = Page()
    page.feed((docs / "index.html").read_text())
    ids = [attrs["id"] for _, attrs in page.elements if "id" in attrs]
    assert len(ids) == len(set(ids))
    assert sum(tag == "h1" for tag, _ in page.elements) == 1
    assert ("html", {"lang": "en"}) in page.elements
    for tag, attrs in page.elements:
        for key in ("href", "src"):
            if key not in attrs:
                continue
            target = attrs[key]
            if target.startswith("#"):
                assert target[1:] in ids
            else:
                assert (docs / target).exists()
        if attrs.get("id") == "launch":
            assert tag == "a" and "href" not in attrs
            assert attrs["aria-disabled"] == "true"
            assert attrs["tabindex"] == "-1"


def test_host_configuration():
    config = tomllib.loads((ROOT / ".streamlit/config.toml").read_text())
    assert config["server"]["headless"] is True
    assert config["server"]["enableStaticServing"] is False
    assert "enableAgentApi" not in config["server"]
    assert '.streamlit/secrets.toml' in (ROOT / '.gitignore').read_text().splitlines()
