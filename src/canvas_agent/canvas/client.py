"""Canvas REST client with host allowlisting and retries."""

from __future__ import annotations

import logging
import random
import time
from datetime import datetime
from typing import Any, Callable
from urllib.parse import urlparse

import httpx

from canvas_agent.canvas import endpoints
from canvas_agent.canvas.parse import html_to_text, parse_control_status
from canvas_agent.models import DiscussionEntry, DiscussionSnapshot
from canvas_agent.safety.boundaries import (
    assert_allowed_canvas_path,
    assert_allowed_method,
)

logger = logging.getLogger(__name__)

RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}


class CanvasError(Exception):
    """Base Canvas client error (never includes the API token)."""


class CanvasAuthError(CanvasError):
    pass


class CanvasNotFoundError(CanvasError):
    pass


class CanvasTransientError(CanvasError):
    """Transient / ambiguous failure. Safe to retry for reads; not for blind write retries."""


class CanvasAmbiguousWriteError(CanvasTransientError):
    """Write may or may not have reached Canvas; do not retry POST—reconcile instead."""


class CanvasClient:
    """Deterministic Canvas API access.

    Blast radius:
    - Own token from env/secrets only (never logged)
    - Allowlisted Canvas host only
    - GET + create POST only (no PUT/PATCH/DELETE → cannot edit/delete others)
    - Homework discussion topic paths only
    """

    def __init__(
        self,
        base_url: str,
        token: str,
        course_id: int,
        topic_id: int,
        *,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 30.0,
        max_retries: int = 5,
        backoff_base: float = 1.0,
        backoff_cap: float = 30.0,
        sleep_fn: Callable[[float], None] | None = None,
        rng: random.Random | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        # Keep token only for Authorization header; never include in logs/errors.
        self._token = token
        self.course_id = course_id
        self.topic_id = topic_id
        self._max_retries = max_retries
        self._backoff_base = backoff_base
        self._backoff_cap = backoff_cap
        self._sleep = sleep_fn or time.sleep
        self._rng = rng or random.Random()

        host = urlparse(self._base_url).hostname
        if not host:
            raise ValueError("Invalid Canvas base URL")
        self._allowed_hosts = {host.lower()}

        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "User-Agent": "canvas-agent/0.1",
        }
        self._client = httpx.Client(
            base_url=self._base_url,
            headers=headers,
            timeout=timeout,
            transport=transport,
            follow_redirects=True,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> CanvasClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def _assert_allowed(self, url: str) -> None:
        parsed = urlparse(url if "://" in url else f"{self._base_url}{url}")
        host = (parsed.hostname or "").lower()
        if host and host not in self._allowed_hosts:
            raise CanvasError(f"Blocked network host: {host}")

    def _backoff_seconds(self, attempt: int, retry_after: str | None) -> float:
        if retry_after:
            try:
                return min(self._backoff_cap, float(retry_after))
            except ValueError:
                pass
        ceiling = min(self._backoff_cap, self._backoff_base * (2**attempt))
        return self._rng.random() * ceiling

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        allow_retry: bool = True,
    ) -> httpx.Response:
        """HTTP helper.

        Reads may retry transient failures. Writes must pass allow_retry=False so a
        lost acknowledgement cannot become a duplicate POST.
        """
        try:
            assert_allowed_method(method)
            assert_allowed_canvas_path(path, self.course_id, self.topic_id)
        except PermissionError as exc:
            raise CanvasError(str(exc)) from exc
        self._assert_allowed(path)
        max_attempts = self._max_retries + 1 if allow_retry else 1
        last_error: Exception | None = None
        for attempt in range(max_attempts):
            try:
                response = self._client.request(method, path, params=params, data=data)
            except (httpx.TimeoutException, httpx.NetworkError, httpx.TransportError) as exc:
                err_cls = (
                    CanvasAmbiguousWriteError
                    if method.upper() != "GET"
                    else CanvasTransientError
                )
                last_error = err_cls(f"{type(exc).__name__}")
                if attempt >= max_attempts - 1:
                    break
                delay = self._backoff_seconds(attempt, None)
                logger.warning(
                    "Canvas network error on %s %s (attempt %s): %s; sleep %.2fs",
                    method,
                    path,
                    attempt + 1,
                    type(exc).__name__,
                    delay,
                )
                self._sleep(delay)
                continue

            if response.status_code in {401, 403}:
                raise CanvasAuthError(
                    f"Canvas auth failed with status {response.status_code}"
                )
            if response.status_code == 404:
                raise CanvasNotFoundError(f"Canvas resource not found: {path}")
            if response.status_code in RETRYABLE_STATUS:
                last_error = CanvasTransientError(
                    f"Canvas transient status {response.status_code}"
                )
                if not allow_retry or attempt >= max_attempts - 1:
                    # Ambiguous for writes: server may have applied the POST.
                    if method.upper() != "GET":
                        raise CanvasAmbiguousWriteError(
                            f"Canvas write got status {response.status_code}"
                        )
                    break
                delay = self._backoff_seconds(
                    attempt, response.headers.get("Retry-After")
                )
                logger.warning(
                    "Canvas status %s on %s %s (attempt %s); sleep %.2fs",
                    response.status_code,
                    method,
                    path,
                    attempt + 1,
                    delay,
                )
                self._sleep(delay)
                continue
            if response.status_code >= 400:
                raise CanvasError(f"Canvas error status {response.status_code}")
            return response

        assert last_error is not None
        raise last_error

    def get_self_user_id(self) -> int:
        response = self._request("GET", endpoints.users_self())
        try:
            payload = response.json()
            return int(payload["id"])
        except (ValueError, KeyError, TypeError) as exc:
            raise CanvasError("Malformed Canvas /users/self response") from exc

    def get_topic(self) -> dict[str, Any]:
        response = self._request(
            "GET", endpoints.discussion_topic(self.course_id, self.topic_id)
        )
        try:
            payload = response.json()
        except ValueError as exc:
            raise CanvasError("Malformed Canvas topic JSON") from exc
        if not isinstance(payload, dict):
            raise CanvasError("Malformed Canvas topic response")
        return payload

    def get_control_status(self) -> tuple[Any, str]:
        topic = self.get_topic()
        message = topic.get("message") or ""
        return parse_control_status(message), html_to_text(message)

    def get_discussion_view(self) -> DiscussionSnapshot:
        response = self._request(
            "GET", endpoints.discussion_view(self.course_id, self.topic_id)
        )
        try:
            payload = response.json()
        except ValueError as exc:
            raise CanvasError("Malformed Canvas discussion view JSON") from exc
        if not isinstance(payload, dict):
            raise CanvasError("Malformed Canvas discussion view response")
        # Control line comes from topic fetch; view may not include topic message.
        topic = self.get_topic()
        message_html = topic.get("message") or ""
        entries = self._flatten_view(payload.get("view") or [])
        return DiscussionSnapshot(
            topic_id=self.topic_id,
            control_status=parse_control_status(message_html),
            topic_message_text=html_to_text(message_html),
            entries=entries,
        )

    def _flatten_view(
        self, nodes: list[dict[str, Any]], parent_id: int | None = None
    ) -> list[DiscussionEntry]:
        flat: list[DiscussionEntry] = []
        for node in nodes:
            if not isinstance(node, dict) or "id" not in node:
                raise CanvasError("Malformed Canvas discussion entry")
            entry_id = int(node["id"])
            created = node.get("created_at")
            created_at = None
            if created:
                try:
                    created_at = datetime.fromisoformat(created.replace("Z", "+00:00"))
                except ValueError:
                    created_at = None
            flat.append(
                DiscussionEntry(
                    id=entry_id,
                    user_id=node.get("user_id"),
                    parent_id=node.get("parent_id", parent_id),
                    message_text=html_to_text(node.get("message") or ""),
                    created_at=created_at,
                )
            )
            replies = node.get("replies") or []
            if replies:
                flat.extend(self._flatten_view(replies, parent_id=entry_id))
        return flat

    def create_entry(self, message: str) -> dict[str, Any]:
        # Single attempt only — never blind-retry POSTs.
        response = self._request(
            "POST",
            endpoints.discussion_entries(self.course_id, self.topic_id),
            data={"message": message},
            allow_retry=False,
        )
        try:
            payload = response.json()
            int(payload["id"])
        except (ValueError, KeyError, TypeError) as exc:
            raise CanvasAmbiguousWriteError(
                "Malformed create-entry response; reconcile before retry"
            ) from exc
        return payload

    def create_reply(self, entry_id: int, message: str) -> dict[str, Any]:
        response = self._request(
            "POST",
            endpoints.discussion_replies(self.course_id, self.topic_id, entry_id),
            data={"message": message},
            allow_retry=False,
        )
        try:
            payload = response.json()
            int(payload["id"])
        except (ValueError, KeyError, TypeError) as exc:
            raise CanvasAmbiguousWriteError(
                "Malformed create-reply response; reconcile before retry"
            ) from exc
        return payload

    def get_entries_by_ids(self, entry_ids: list[int]) -> list[dict[str, Any]]:
        if not entry_ids:
            return []
        params: list[tuple[str, str]] = [("ids[]", str(i)) for i in entry_ids]
        path = endpoints.discussion_entry_list(self.course_id, self.topic_id)
        try:
            assert_allowed_method("GET")
            assert_allowed_canvas_path(path, self.course_id, self.topic_id)
        except PermissionError as exc:
            raise CanvasError(str(exc)) from exc
        self._assert_allowed(path)
        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                response = self._client.get(path, params=params)
            except (httpx.TimeoutException, httpx.NetworkError, httpx.TransportError) as exc:
                last_error = CanvasTransientError(type(exc).__name__)
                if attempt >= self._max_retries:
                    break
                self._sleep(self._backoff_seconds(attempt, None))
                continue
            if response.status_code in RETRYABLE_STATUS:
                last_error = CanvasTransientError(
                    f"Canvas transient status {response.status_code}"
                )
                if attempt >= self._max_retries:
                    break
                self._sleep(
                    self._backoff_seconds(attempt, response.headers.get("Retry-After"))
                )
                continue
            if response.status_code in {401, 403}:
                raise CanvasAuthError(
                    f"Canvas auth failed with status {response.status_code}"
                )
            if response.status_code >= 400:
                raise CanvasError(f"Canvas error status {response.status_code}")
            try:
                payload = response.json()
            except ValueError as exc:
                raise CanvasError("Malformed Canvas entry_list JSON") from exc
            if not isinstance(payload, list):
                raise CanvasError("Malformed Canvas entry_list response")
            return payload
        assert last_error is not None
        raise last_error

    def verify_entry(self, entry_id: int) -> dict[str, Any] | None:
        entries = self.get_entries_by_ids([entry_id])
        for entry in entries:
            if int(entry.get("id", -1)) == entry_id:
                return entry
        # Fallback: scan full view
        snapshot = self.get_discussion_view()
        for entry in snapshot.entries:
            if entry.id == entry_id:
                return {
                    "id": entry.id,
                    "user_id": entry.user_id,
                    "parent_id": entry.parent_id,
                    "message": entry.message_text,
                }
        return None
