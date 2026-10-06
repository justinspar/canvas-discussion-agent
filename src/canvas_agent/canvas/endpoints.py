"""Canvas REST path builders (course-scoped discussion endpoints only).

No edit/delete paths are exposed. Activity is limited to Homework 3
discussion topic reads and create entry/reply writes.
"""

from __future__ import annotations

from canvas_agent.safety.boundaries import is_allowed_canvas_path


def users_self() -> str:
    return "/api/v1/users/self"


def discussion_topic(course_id: int, topic_id: int) -> str:
    return f"/api/v1/courses/{course_id}/discussion_topics/{topic_id}"


def discussion_view(course_id: int, topic_id: int) -> str:
    return f"/api/v1/courses/{course_id}/discussion_topics/{topic_id}/view"


def discussion_entries(course_id: int, topic_id: int) -> str:
    return f"/api/v1/courses/{course_id}/discussion_topics/{topic_id}/entries"


def discussion_replies(course_id: int, topic_id: int, entry_id: int) -> str:
    return (
        f"/api/v1/courses/{course_id}/discussion_topics/{topic_id}"
        f"/entries/{entry_id}/replies"
    )


def discussion_entry_list(course_id: int, topic_id: int) -> str:
    return f"/api/v1/courses/{course_id}/discussion_topics/{topic_id}/entry_list"


def path_in_homework_scope(path: str, course_id: int, topic_id: int) -> bool:
    """Re-export allowlist check used by the Canvas client."""
    return is_allowed_canvas_path(path, course_id, topic_id)
