"""Generate a static full text search index of published Pelican content."""
import json
from html.parser import HTMLParser
from pathlib import Path
from pelican import signals


class Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.ignored = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.ignored += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.ignored = max(0, self.ignored - 1)

    def handle_data(self, data):
        if not self.ignored:
            self.parts.append(data)


def plain_text(value):
    parser = Text()
    parser.feed(str(value))
    return " ".join(" ".join(parser.parts).split())


def build_index(generators):
    entries = []
    for generator in generators:
        for item in [*getattr(generator, "pages", []), *getattr(generator, "articles", [])]:
            if item.status == "published":
                entries.append({"title": plain_text(item.title), "url": item.url,
                                "text": plain_text(item.content)})
    output = Path(generators[0].settings["OUTPUT_PATH"])
    output.mkdir(parents=True, exist_ok=True)
    data = json.dumps(entries, ensure_ascii=True).replace("<", "\\u003c")
    (output / "search-index.js").write_text("window.SITE_SEARCH_INDEX = " + data + ";\n", encoding="utf-8")


def register():
    signals.all_generators_finalized.connect(build_index)
