"""SQL safety checks: the agent may read, never write."""
from __future__ import annotations

import re

# Statements that change data or schema. Matched as whole words, case-insensitive.
_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|truncate|grant|revoke|merge|"
    r"call|do|copy|vacuum|reindex|cluster|comment|lock|listen|notify|"
    r"refresh|security|set|reset|discard|execute|prepare|deallocate)\b",
    re.IGNORECASE,
)
_COMMENT = re.compile(r"(--[^\n]*|/\*.*?\*/)", re.DOTALL)


class UnsafeQueryError(ValueError):
    """Raised when a query is not a single read-only statement."""


def strip_comments(sql: str) -> str:
    return _COMMENT.sub(" ", sql)


def validate_read_only(sql: str) -> str:
    """Return the cleaned SQL if it is a single SELECT/WITH/EXPLAIN statement.

    Raises UnsafeQueryError otherwise.
    """
    cleaned = strip_comments(sql).strip().rstrip(";").strip()
    if not cleaned:
        raise UnsafeQueryError("Empty query.")
    if ";" in cleaned:
        raise UnsafeQueryError("Only one statement is allowed per call.")
    first = cleaned.split(None, 1)[0].lower()
    if first not in {"select", "with", "explain", "show", "table", "values"}:
        raise UnsafeQueryError(
            f"Only read-only queries are allowed (got '{first.upper()}')."
        )
    if _FORBIDDEN.search(cleaned):
        raise UnsafeQueryError("Query contains a forbidden keyword.")
    return cleaned


def apply_row_limit(sql: str, max_rows: int) -> str:
    """Wrap the query so it can never return more than max_rows rows."""
    return f"SELECT * FROM ({sql}) AS _limited LIMIT {int(max_rows)}"
