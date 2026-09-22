"""Read-only preview of a specifically reviewed local source pack."""
from dataclasses import dataclass
from hashlib import sha256
from html.parser import HTMLParser
import json
import re
import unicodedata
from pathlib import Path
from zipfile import ZipFile

S59_DIGEST = "6dd22c5279e26958c55b94eefd00834e9a2b061b39fea5186de8d5806cee5b87"
TOPICS = ("greeting", "drawing-origins", "drawing-experience", "art-feedback", "family", "composition")
# Reviewed *preview* choices, not a general inference engine or relationship model.
_CHOICES = {
    "drawing-origins": (("T02", "最初是母亲教她画画。"), ("T01", "小时候画过自然题材和带画的明信片。")),
    "drawing-experience": (("T04", "从小开始画画，已有多年绘画经验。"),),
    "art-feedback": (("T03", "她回忆母亲曾称赞她画得好，童年画画令她开心。"),),
}
_BLOCKED = {
    "T05": "time-not-established", "T06": "time-not-established", "T07": "time-not-established",
    "T08": "interpretation-only", "T09": "private-background",
    "T10": "not-established", "T11": "wrong-subject",
}


@dataclass(frozen=True)
class BasisPreviewRequest:
    topic: str


@dataclass(frozen=True)
class BasisMessageRequest:
    message: str


# Whole-message contracts. Do not use a substring hit to disclose a memory.
_MESSAGE_TOPICS = (
    ("drawing-origins", r"你(?:是)?(?:怎么|如何)开始(?:画画|学画)(?:的)?(?:呢|呀|啊)?", ("T02", "T01")),
    ("drawing-origins", r"(?:最初)?(?:是)?谁教你画画的(?:呢)?", ("T02",)),
    ("drawing-origins", r"你小时候(?:都)?画(?:过)?(?:些)?什么(?:呢)?", ("T01",)),
    ("drawing-experience", r"你(?:画画|学画)(?:有)?多久了(?:呢)?|你画了多少年(?:了)?|你(?:是)?什么时候开始(?:画画|学画)的(?:呢)?", ("T04",)),
    ("art-feedback", r"有人夸过你的画吗|你(?:的画|画的画)(?:以前|曾经)?得到过什么评价|你(?:以前|曾经)?收到过(?:什么|怎样的)(?:绘画反馈|画作评价)", ("T03",)),
    ("greeting", r"你好|嗨|你好呀", ()),
    ("composition", r"插画的背景一定要很复杂才好吗|背景一定要画得很复杂吗", ()),
)


def _message_selection(message: str) -> tuple[str, tuple[str, ...]] | None:
    text = re.sub(r"\s+", "", unicodedata.normalize("NFKC", message)).rstrip("。！？!?")
    text = re.sub(r"^(?:你好|嗨)[,，]", "", text, count=1)
    for topic, pattern, item_ids in _MESSAGE_TOPICS:
        if re.fullmatch(pattern, text):
            return topic, item_ids
    return None


@dataclass(frozen=True)
class BasisItemView:
    item_id: str
    title: str
    text: str
    reason: str
    citations: tuple[str, ...] = ()


@dataclass(frozen=True)
class BasisPreview:
    status: str
    code: str = ""
    topic: str = ""
    selected: tuple[BasisItemView, ...] = ()
    excluded: tuple[BasisItemView, ...] = ()
    basis_digest: str = ""


class _Paragraphs(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows = []
        self.buf = None

    def handle_starttag(self, tag, attrs):
        if tag == "p":
            if self.buf is not None:
                self.rows.append("".join(self.buf).strip())
            self.buf = []

    def handle_data(self, data):
        if self.buf is not None:
            self.buf.append(data)

    def handle_endtag(self, tag):
        if tag == "p" and self.buf is not None:
            self.rows.append("".join(self.buf).strip())
            self.buf = None


class ConversationBasisPreview:
    """Owns integrity checks and selection. No model, store, or fact-writing port."""

    def __init__(self, pack_path: Path, source_root: Path, *, expected_digest: str):
        if (not isinstance(pack_path, Path) or not pack_path.is_absolute()
                or not isinstance(source_root, Path) or not source_root.is_absolute()
                or len(expected_digest) != 64
                or any(c not in "0123456789abcdef" for c in expected_digest)):
            raise ValueError("explicit reviewed local basis required")
        self._pack = pack_path
        self._sources = source_root
        self._digest = expected_digest

    def _verified_items(self):
        with self._pack.open("rb") as stream:
            data = stream.read(2_000_001)
        if len(data) > 2_000_000 or sha256(data).hexdigest() != self._digest:
            raise ValueError("basis changed")
        pack = json.loads(data)
        items = pack["items"]
        if (pack["version"] != "conversation-basis-0.2"
                or pack["status"] != "local-review-only-not-runtime"
                or pack["established_runtime_life_events"] != []
                or len(items) != 11
                or {it["id"] for it in items} != {f"T{i:02}" for i in range(1, 12)}):
            raise ValueError("unreviewed schema")
        # Cache only within this preview; every subsequent preview rechecks disk.
        books, documents = {}, {}
        for item in items:
            if item["id"] != "T10" and not item["evidence"]:
                raise ValueError("missing citation")
            for ref in item["evidence"]:
                name = ref["file"]
                if not isinstance(name, str) or Path(name).name != name or "/" in name or "\\" in name:
                    raise ValueError("invalid source name")
                path = (self._sources / name).resolve(strict=True)
                if not path.is_relative_to(self._sources.resolve(strict=True)):
                    raise ValueError("source escapes supplied root")
                if path not in books:
                    with path.open("rb") as stream:
                        books[path] = stream.read(32_000_001)
                raw = books[path]
                if len(raw) > 32_000_000 or sha256(raw).hexdigest() != ref["file_sha256"]:
                    raise ValueError("source changed")
                key = (path, ref["href"])
                if key not in documents:
                    from io import BytesIO
                    with ZipFile(BytesIO(raw)) as archive:
                        info = archive.getinfo(ref["href"])
                        if info.file_size > 2_000_000:
                            raise ValueError("document exceeds preview limit")
                        content = archive.read(info)
                    parser = _Paragraphs()
                    parser.feed(content.decode("utf-8-sig"))
                    parser.close()
                    documents[key] = (sha256(content).hexdigest(), parser.rows)
                digest, rows = documents[key]
                n = ref["paragraph"]
                if (digest != ref["document_sha256"] or type(n) is not int or not 1 <= n <= len(rows)
                        or rows[n - 1] != ref["quote"]
                        or sha256(rows[n - 1].encode()).hexdigest() != ref["quote_sha256"]):
                    raise ValueError("citation mismatch")
        return {it["id"]: it for it in items}

    def preview(self, request: object) -> BasisPreview:
        allowed_ids = None
        if type(request) is BasisMessageRequest:
            if not isinstance(request.message, str) or not request.message.strip() or len(request.message) > 1000:
                return BasisPreview("rejected", "invalid-message")
            selection = _message_selection(request.message)
            if selection is None:
                return BasisPreview("no-op", "message-not-matched")
            topic, allowed_ids = selection
            request = BasisPreviewRequest(topic)
        if type(request) is not BasisPreviewRequest or request.topic not in TOPICS:
            return BasisPreview("rejected", "unknown-topic")
        try:
            items = self._verified_items()
        except FileNotFoundError:
            return BasisPreview("unavailable", "basis-or-source-missing", request.topic)
        except Exception:
            return BasisPreview("failed-closed", "basis-integrity-failed", request.topic)
        selected = []
        for key, summary in _CHOICES.get(request.topic, ()):
            if allowed_ids is not None and key not in allowed_ids:
                continue
            item = items[key]
            citations = tuple(f"{r['file']} / {r['href']} / p{r['paragraph']}" for r in item["evidence"])
            selected.append(BasisItemView(key, item["title"], summary, "explicit-topic-preview", citations))
        excluded = tuple(BasisItemView(key, item["title"], "", _BLOCKED.get(key, "not-needed-for-topic"))
                         for key, item in sorted(items.items()) if key not in {v.item_id for v in selected})
        if len(selected) > 2 or sum(len(v.text) for v in selected) > 400:
            return BasisPreview("failed-closed", "preview-budget-exceeded", request.topic)
        return BasisPreview("ready" if selected else "no-op", "", request.topic,
                            tuple(selected), excluded, self._digest)
