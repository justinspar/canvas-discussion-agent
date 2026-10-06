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

logger = logging.getLogger(__name__)

RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}


class CanvasError(Exception):
    """Base Canvas client error (never includes the API token)."""


class CanvasAuthError(CanvasError):
    pass


class CanvasNotFoundError(CanvasError):
    pass


class CanvasTransientError(CanvasError):
    pass


class CanvasClient:
    """Deterministic Canvas API access. Exposes only GET + create POST."""

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
    ) -> httpx.Response:
        self._assert_allowed(path)
        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                response = self._client.request(method, path, params=params, data=data)
            except (httpx.TimeoutException, httpx.NetworkError, httpx.TransportError) as exc:
                last_error = CanvasTransientError(str(exc))
                if attempt >= self._max_retries:
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
                if attempt >= self._max_retries:
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
        payload = response.json()
        return int(payload["id"])

    def get_topic(self) -> dict[str, Any]:
        response = self._request(
            "GET", endpoints.discussion_topic(self.course_id, self.topic_id)
        )
        return response.json()

    def get_control_status(self) -> tuple[Any, str]:
        topic = self.get_topic()
        message = topic.get("message") or ""
        return parse_control_status(message), html_to_text(message)

    def get_discussion_view(self) -> DiscussionSnapshot:
        response = self._request(
            "GET", endpoints.discussion_view(self.course_id, self.topic_id)
        )
        payload = response.json()
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
        response = self._request(
            "POST",
            endpoints.discussion_entries(self.course_id, self.topic_id),
            data={"message": message},
        )
        return response.json()

    def create_reply(self, entry_id: int, message: str) -> dict[str, Any]:
        response = self._request(
            "POST",
            endpoints.discussion_replies(self.course_id, self.topic_id, entry_id),
            data={"message": message},
        )
        return response.json()

    def get_entries_by_ids(self, entry_ids: list[int]) -> list[dict[str, Any]]:
        if not entry_ids:
            return []
        params: list[tuple[str, str]] = [("ids[]", str(i)) for i in entry_ids]
        # httpx accepts list of tuples for repeated params
        self._assert_allowed(endpoints.discussion_entry_list(self.course_id, self.topic_id))
        last_error: Exception | None = None
        path = endpoints.discussion_entry_list(self.course_id, self.topic_id)
        for attempt in range(self._max_retries + 1):
            try:
                response = self._client.get(path, params=params)
            except (httpx.TimeoutException, httpx.NetworkError, httpx.TransportError) as exc:
                last_error = CanvasTransientError(str(exc))
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
            return response.json()
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
