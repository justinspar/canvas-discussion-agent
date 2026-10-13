"""Parse Canvas HTML topic bodies and discussion messages."""

from __future__ import annotations

import hashlib
import html
import re
from html.parser import HTMLParser

from canvas_agent.models import ControlStatus

_CONTROL_RUNNING = "COURSE-TEAM CONTROL: RUNNING"
_CONTROL_PAUSED = "COURSE-TEAM CONTROL: PAUSED"
_WHITESPACE_RE = re.compile(r"\s+")
_FENCE_RE = re.compile(r"```(?:([A-Za-z0-9_+-]+)\n)?(.*?)```", re.DOTALL)
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_LOOKS_LIKE_HTML_RE = re.compile(
    r"<\s*(p|br|ul|ol|li|pre|code|strong|b|em|blockquote)\b",
    re.IGNORECASE,
)

ALLOWED_CANVAS_TAGS = frozenset(
    {"p", "br", "strong", "b", "em", "ul", "ol", "li", "pre", "code", "blockquote"}
)


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._chunks: list[str] = []
        self._skip = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style"}:
            self._skip = True
        if tag in {"br", "p", "div", "li", "tr", "h1", "h2", "h3", "h4"}:
            self._chunks.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"}:
            self._skip = False
        if tag in {"pre", "code", "p", "div", "li", "tr"}:
            self._chunks.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self._chunks.append(data)

    def text(self) -> str:
        return "".join(self._chunks)


class _AllowlistSanitizer(HTMLParser):
    """Rebuild HTML keeping only allowlisted tags with no attributes."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._out: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style"}:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag in ALLOWED_CANVAS_TAGS:
            if tag == "br":
                self._out.append("<br>")
            else:
                self._out.append(f"<{tag}>")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"}:
            if self._skip_depth:
                self._skip_depth -= 1
            return
        if self._skip_depth:
            return
        if tag in ALLOWED_CANVAS_TAGS and tag != "br":
            self._out.append(f"</{tag}>")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._skip_depth:
            return
        if tag == "br":
            self._out.append("<br>")

    def handle_data(self, data: str) -> None:
        if not self._skip_depth:
            self._out.append(html.escape(data, quote=False))

    def result(self) -> str:
        return "".join(self._out)


def html_to_text(raw: str | None) -> str:
    if not raw:
        return ""
    parser = _HTMLTextExtractor()
    try:
        parser.feed(raw)
        parser.close()
        text = parser.text()
    except Exception:
        text = re.sub(r"<[^>]+>", " ", raw)
    text = html.unescape(text)
    lines = [line.rstrip() for line in text.replace("\r\n", "\n").split("\n")]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines)


def sanitize_canvas_html(raw: str) -> str:
    """Keep only allowlisted Canvas tags; drop attributes and scripts."""
    parser = _AllowlistSanitizer()
    try:
        parser.feed(raw or "")
        parser.close()
        return parser.result().strip()
    except Exception:
        return html.escape(raw or "").replace("\n", "<br>\n")


def looks_like_html(message: str) -> bool:
    return bool(_LOOKS_LIKE_HTML_RE.search(message or ""))


def _inline_format(text: str) -> str:
    parts: list[str] = []
    pos = 0
    for match in _BOLD_RE.finditer(text):
        parts.append(html.escape(text[pos : match.start()], quote=False))
        parts.append(
            "<strong>" + html.escape(match.group(1), quote=False) + "</strong>"
        )
        pos = match.end()
    parts.append(html.escape(text[pos:], quote=False))
    return "".join(parts)


def _block_to_html(block: str) -> str:
    lines = block.split("\n")
    nonempty = [ln for ln in lines if ln.strip()]
    if not nonempty:
        return ""

    bullet = all(re.match(r"^\s*[-*]\s+\S", ln) for ln in nonempty)
    numbered = all(re.match(r"^\s*\d+\.\s+\S", ln) for ln in nonempty)
    if bullet:
        items = [
            f"<li>{_inline_format(re.sub(r'^\s*[-*]\s+', '', ln))}</li>"
            for ln in nonempty
        ]
        return "<ul>" + "".join(items) + "</ul>"
    if numbered:
        items = [
            f"<li>{_inline_format(re.sub(r'^\s*\d+\.\s+', '', ln))}</li>"
            for ln in nonempty
        ]
        return "<ol>" + "".join(items) + "</ol>"

    joined = "<br>\n".join(_inline_format(ln) for ln in lines if ln.strip())
    return f"<p>{joined}</p>" if joined else ""


def plain_text_to_canvas_html(message: str) -> str:
    """
    Convert agent text to peer-like Canvas HTML.
    If message already contains allowlisted HTML, sanitize and return.
    Otherwise convert markdown-ish plain text (paragraphs, lists, bold, fences).
    """
    text = (message or "").replace("\r\n", "\n").strip()
    if not text:
        return ""
    if looks_like_html(text):
        return sanitize_canvas_html(text)

    parts: list[str] = []
    pos = 0
    for match in _FENCE_RE.finditer(text):
        before = text[pos : match.start()]
        if before.strip():
            for block in re.split(r"\n\s*\n", before.strip()):
                html_block = _block_to_html(block)
                if html_block:
                    parts.append(html_block)
        code = html.escape(match.group(2) or "", quote=False)
        parts.append(f"<pre><code>{code}</code></pre>")
        pos = match.end()
    tail = text[pos:]
    if tail.strip():
        for block in re.split(r"\n\s*\n", tail.strip()):
            html_block = _block_to_html(block)
            if html_block:
                parts.append(html_block)
    return "\n".join(parts) if parts else f"<p>{_inline_format(text)}</p>"


# Alias used by client write path
to_canvas_html = plain_text_to_canvas_html


def first_nonempty_line(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


def parse_control_status(topic_message_html: str | None) -> ControlStatus:
    """Parse the first control line from a topic description/message body.

    Only exact RUNNING or PAUSED counts as confident. Anything else is UNKNOWN,
    which must be treated as do-not-post.
    """
    text = html_to_text(topic_message_html)
    first = first_nonempty_line(text).upper()
    normalized = _WHITESPACE_RE.sub(" ", first).strip()
    if normalized == _CONTROL_RUNNING:
        return ControlStatus.RUNNING
    if normalized == _CONTROL_PAUSED:
        return ControlStatus.PAUSED
    return ControlStatus.UNKNOWN


def normalize_message(text: str) -> str:
    plain = html_to_text(text) if "<" in text and ">" in text else text
    plain = _WHITESPACE_RE.sub(" ", plain).strip().casefold()
    return plain


def content_fingerprint(message: str, parent_id: int | None) -> str:
    # Canonicalize through the same HTML path Canvas receives so plain/markdown
    # drafts fingerprint the same as html_to_text(readback).
    canonical = normalize_message(to_canvas_html(message) if message else "")
    material = f"{canonical}|{parent_id}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()
