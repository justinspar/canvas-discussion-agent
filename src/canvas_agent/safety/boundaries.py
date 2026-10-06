"""Hard blast-radius limits for Homework 3 agent activity.

The agent may only use its own Canvas token (from env/secrets), talk to the
configured Canvas host and LLM host, and create discussion entries/replies.
It never edits/deletes others' posts, never talks to Piazza, and never expands
credentials or network scope at runtime.
"""

from __future__ import annotations

from urllib.parse import urlparse

# HTTP verbs the Canvas client is allowed to use.
ALLOWED_HTTP_METHODS = frozenset({"GET", "POST"})

# Mutating verbs that would edit/delete contributions — always blocked.
FORBIDDEN_HTTP_METHODS = frozenset({"PUT", "PATCH", "DELETE"})


def normalize_api_path(path: str) -> str:
    """Strip query/fragment and trailing slash for allowlist checks."""
    parsed = urlparse(path if "://" in path else f"https://canvas.local{path}")
    clean = parsed.path or "/"
    if clean != "/" and clean.endswith("/"):
        clean = clean.rstrip("/")
    return clean


def is_allowed_canvas_path(path: str, course_id: int, topic_id: int) -> bool:
    """True only for the homework discussion endpoints (+ /users/self)."""
    clean = normalize_api_path(path)
    base = f"/api/v1/courses/{course_id}/discussion_topics/{topic_id}"
    allowed = {
        "/api/v1/users/self",
        base,
        f"{base}/view",
        f"{base}/entries",
        f"{base}/entry_list",
    }
    if clean in allowed:
        return True
    # POST replies: .../entries/{id}/replies
    prefix = f"{base}/entries/"
    if clean.startswith(prefix) and clean.endswith("/replies"):
        mid = clean[len(prefix) : -len("/replies")]
        return mid.isdigit() and mid != ""
    return False


def assert_allowed_method(method: str) -> None:
    upper = method.upper()
    if upper in FORBIDDEN_HTTP_METHODS:
        raise PermissionError(
            f"Blocked Canvas method {upper}: agent must not edit or delete contributions"
        )
    if upper not in ALLOWED_HTTP_METHODS:
        raise PermissionError(f"Blocked Canvas method {upper}")


def assert_allowed_canvas_path(path: str, course_id: int, topic_id: int) -> None:
    if not is_allowed_canvas_path(path, course_id, topic_id):
        raise PermissionError(
            "Blocked Canvas path outside Homework 3 discussion scope"
        )
