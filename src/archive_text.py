from html.parser import HTMLParser
import re


class ArchiveTextParser(HTMLParser):

    BLOCKS = {
        "p", "div", "section", "article",
        "h1", "h2", "h3", "h4",
        "blockquote", "li", "ul", "ol",
        "br", "tr",
    }

    def __init__(self):

        super().__init__(convert_charrefs=True)

        self.parts = []
        self.ignored = 0

    def handle_starttag(self, tag, attrs):

        if tag in ("script", "style"):
            self.ignored += 1
            return

        if self.ignored:
            return

        if tag in self.BLOCKS:
            self.parts.append("\n")

        if tag == "li":
            self.parts.append("• ")

    def handle_endtag(self, tag):

        if tag in ("script", "style"):
            self.ignored = max(0, self.ignored - 1)
            return

        if not self.ignored and tag in self.BLOCKS:
            self.parts.append("\n")

    def handle_data(self, data):

        if not self.ignored:
            self.parts.append(data)


def archive_plain_text(value):

    text = str(value or "")

    if not re.search(r"</?[a-zA-Z][^>]*>", text):
        return text

    parser = ArchiveTextParser()
    parser.feed(text)
    parser.close()

    result = "".join(parser.parts)

    return re.sub(
        r"\n{3,}",
        "\n\n",
        result,
    ).strip()
