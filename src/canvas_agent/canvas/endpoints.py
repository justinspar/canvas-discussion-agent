"""Canvas REST path builders (course-scoped discussion endpoints only)."""

from __future__ import annotations


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
