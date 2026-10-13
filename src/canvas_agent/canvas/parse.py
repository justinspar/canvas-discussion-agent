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


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._chunks: list[str] = []
        self._skip = False
        self._pre = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style"}:
            self._skip = True
        if tag in {"pre", "code"}:
            self._pre = True
        if tag in {"br", "p", "div", "li", "tr", "h1", "h2", "h3", "h4"}:
            self._chunks.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"}:
            self._skip = False
        if tag in {"pre", "code"}:
            self._pre = False
            self._chunks.append("\n")
        if tag in {"p", "div", "li", "tr"}:
            self._chunks.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self._chunks.append(data)

    def text(self) -> str:
        return "".join(self._chunks)


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
    # Keep indentation (needed for code); trim trailing spaces only.
    lines = [line.rstrip() for line in text.replace("\r\n", "\n").split("\n")]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines)


_FENCE_RE = re.compile(r"```(?:([A-Za-z0-9_+-]+)\n)?(.*?)```", re.DOTALL)


def plain_text_to_canvas_html(message: str) -> str:
    """
    Convert agent plain text to Canvas HTML that preserves newlines and code fences.
    Plain POSTs otherwise collapse indentation (breaking pytest source blocks).
    """
    text = (message or "").replace("\r\n", "\n")
    parts: list[str] = []
    pos = 0
    for match in _FENCE_RE.finditer(text):
        before = text[pos : match.start()]
        if before:
            parts.append(
                html.escape(before).replace("\n", "<br>\n")
            )
        code = html.escape(match.group(2) or "")
        parts.append(f"<pre><code>{code}</code></pre>\n")
        pos = match.end()
    tail = text[pos:]
    if tail:
        parts.append(html.escape(tail).replace("\n", "<br>\n"))
    return "".join(parts) if parts else html.escape(text).replace("\n", "<br>\n")


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
    # Allow minor whitespace differences around the colon
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
    material = f"{normalize_message(message)}|{parent_id}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()
