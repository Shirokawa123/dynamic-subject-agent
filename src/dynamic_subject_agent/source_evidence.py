"""Local evidence integrity, independent of what a character knows."""
from hashlib import sha256
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile


class SourceText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows = []
        self.nodes = {}
        self._ordinal = 0
        self._buf = None
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1
        if tag == "p":
            if self._buf is not None:
                self.rows.append("".join(self._buf).strip())
            self._buf = []

    def handle_data(self, data):
        self._ordinal += 1
        if not self._skip:
            self.nodes[self._ordinal] = data.strip()
            if self._buf is not None:
                self._buf.append(data)

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip:
            self._skip -= 1
        if tag == "p" and self._buf is not None:
            self.rows.append("".join(self._buf).strip())
            self._buf = None

    def close(self):
        super().close()
        if self._buf is not None:
            self.rows.append("".join(self._buf).strip())
            self._buf = None


def verify_source_evidence(source_root: Path, references: list[dict]) -> None:
    """Verify the exact supplied bytes and locators, never semantic truth."""
    books, documents = {}, {}
    root = source_root.resolve(strict=True)
    for ref in references:
        name = ref["file"]
        if not isinstance(name, str) or Path(name).name != name or "/" in name or "\\" in name:
            raise ValueError("invalid source name")
        path = (root / name).resolve(strict=True)
        if not path.is_relative_to(root):
            raise ValueError("source escapes supplied root")
        if path not in books:
            with path.open("rb") as stream:
                data = stream.read(32_000_001)
            if len(data) > 32_000_000:
                raise ValueError("source exceeds limit")
            books[path] = (data, sha256(data).hexdigest())
        raw, digest = books[path]
        if digest != ref["file_sha256"]:
            raise ValueError("source changed")
        key = (path, ref["href"])
        if key not in documents:
            with ZipFile(BytesIO(raw)) as archive:
                info = archive.getinfo(ref["href"])
                if info.file_size > 2_000_000:
                    raise ValueError("document exceeds limit")
                content = archive.read(info)
            parser = SourceText()
            parser.feed(content.decode("utf-8-sig"))
            parser.close()
            documents[key] = (sha256(content).hexdigest(), parser)
        document_digest, parsed = documents[key]
        if document_digest != ref["document_sha256"]:
            raise ValueError("document changed")
        kind = ref.get("locator_kind", "paragraph")
        if kind == "paragraph":
            n = ref["paragraph"]
            if type(n) is not int or not 1 <= n <= len(parsed.rows):
                raise ValueError("paragraph missing")
            text = parsed.rows[n - 1]
        elif kind == "html_text_node":
            n = ref["text_node"]
            if type(n) is not int or n not in parsed.nodes:
                raise ValueError("text node missing")
            text = parsed.nodes[n]
        else:
            raise ValueError("unsupported locator")
        if not text or text != ref["quote"] or sha256(text.encode()).hexdigest() != ref["quote_sha256"]:
            raise ValueError("citation mismatch")
