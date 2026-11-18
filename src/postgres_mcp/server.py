"""postgres-mcp: a read-only MCP server for PostgreSQL.

Exposes four tools an LLM agent can call:
  - list_tables       : what tables exist
  - describe_table    : columns + types for one table
  - run_query         : execute a single read-only SQL statement
  - campaign_summary  : an example domain tool (voice-AI call campaigns)

Run:  postgres-mcp            (stdio transport, for Claude Desktop / Cursor)
      postgres-mcp --http     (streamable HTTP on :8000, for remote agents)
"""
from __future__ import annotations

import json
import os
import sys
from contextlib import asynccontextmanager
from dataclasses import dataclass
from decimal import Decimal
from datetime import date, datetime
from typing import Any, AsyncIterator

from dotenv import load_dotenv
from mcp.server.fastmcp import Context, FastMCP
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from .safety import UnsafeQueryError, apply_row_limit, validate_read_only

load_dotenv()

MAX_ROWS = int(os.getenv("MAX_ROWS", "200"))
QUERY_TIMEOUT_MS = int(os.getenv("QUERY_TIMEOUT_MS", "5000"))


@dataclass
class AppContext:
    pool: AsyncConnectionPool


@asynccontextmanager
async def lifespan(_: FastMCP) -> AsyncIterator[AppContext]:
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        raise RuntimeError("DATABASE_URL is not set. Copy .env.example to .env.")
    # Every connection is forced read-only and time-limited at the session level,
    # so safety does not rely on keyword filtering alone.
    pool = AsyncConnectionPool(
        dsn,
        min_size=1,
        max_size=5,
        kwargs={
            "options": (
                f"-c default_transaction_read_only=on "
                f"-c statement_timeout={QUERY_TIMEOUT_MS}"
            ),
            "row_factory": dict_row,
        },
        open=False,
    )
    await pool.open()
    try:
        yield AppContext(pool=pool)
    finally:
        await pool.close()


mcp = FastMCP(
    "postgres-mcp",
    instructions=(
        "Read-only access to a PostgreSQL database. Start with list_tables and "
        "describe_table to learn the schema, then use run_query with a single "
        "SELECT. Results are capped at MAX_ROWS; use WHERE/LIMIT for precision."
    ),
    lifespan=lifespan,
)


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _rows_to_json(rows: list[dict[str, Any]]) -> str:
    return json.dumps(
        [{k: _json_safe(v) for k, v in r.items()} for r in rows],
        ensure_ascii=False,
        indent=2,
    )


async def _fetch(ctx: Context, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    pool = ctx.request_context.lifespan_context.pool
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(sql, params)
            return await cur.fetchall()


@mcp.tool()
async def list_tables(ctx: Context, schema: str = "public") -> str:
    """List all tables in a schema with their approximate row counts."""
    rows = await _fetch(
        ctx,
        """
        SELECT c.relname AS table_name,
               c.reltuples::bigint AS approx_rows
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = %s AND c.relkind IN ('r', 'p', 'v', 'm')
        ORDER BY c.relname
        """,
        (schema,),
    )
    return _rows_to_json(rows)


@mcp.tool()
async def describe_table(ctx: Context, table: str, schema: str = "public") -> str:
    """Show columns, data types and nullability for one table."""
    rows = await _fetch(
        ctx,
        """
        SELECT column_name, data_type, is_nullable, column_default
        FROM information_schema.columns
        WHERE table_schema = %s AND table_name = %s
        ORDER BY ordinal_position
        """,
        (schema, table),
    )
    if not rows:
        return json.dumps({"error": f"Table '{schema}.{table}' not found."})
    return _rows_to_json(rows)


@mcp.tool()
async def run_query(ctx: Context, sql: str) -> str:
    """Run ONE read-only SQL statement (SELECT / WITH / EXPLAIN).

    Writes, DDL and multi-statement input are rejected. Output is capped at
    MAX_ROWS rows. Prefer explicit column lists and WHERE clauses.
    """
    try:
        safe_sql = validate_read_only(sql)
    except UnsafeQueryError as exc:
        return json.dumps({"error": str(exc)})
    try:
        rows = await _fetch(ctx, apply_row_limit(safe_sql, MAX_ROWS))
    except Exception as exc:  # surface DB errors to the agent, not a stack trace
        return json.dumps({"error": f"{type(exc).__name__}: {exc}"})
    return json.dumps(
        {"row_count": len(rows), "truncated": len(rows) >= MAX_ROWS,
         "rows": json.loads(_rows_to_json(rows))},
        ensure_ascii=False,
        indent=2,
    )


@mcp.tool()
async def campaign_summary(ctx: Context, campaign_id: int, days: int = 7) -> str:
    """Example domain tool: KPIs for a voice-AI call campaign over the last N days.

    Returns total calls, answered rate, booking rate, average duration, and
    average cost. Assumes a `calls` table (see sql/schema.sql).
    """
    rows = await _fetch(
        ctx,
        """
        SELECT
          COUNT(*)                                            AS total_calls,
          ROUND(AVG((status = 'answered')::int) * 100, 1)     AS answered_pct,
          ROUND(AVG((outcome = 'booked')::int) * 100, 1)      AS booking_pct,
          ROUND(AVG(duration_sec))                            AS avg_duration_sec,
          ROUND(AVG(cost_usd)::numeric, 4)                    AS avg_cost_usd,
          ROUND(AVG(latency_ms))                              AS avg_latency_ms
        FROM calls
        WHERE campaign_id = %s
          AND started_at >= NOW() - (%s || ' days')::interval
        """,
        (campaign_id, str(int(days))),
    )
    return _rows_to_json(rows)


@mcp.resource("schema://{table}")
async def table_schema_resource(table: str) -> str:
    """Expose a table's DDL-like description as an MCP resource."""
    # Resources don't receive Context in all SDK versions; keep this static-ish.
    return f"Use the describe_table tool with table='{table}' for live column info."


def main() -> None:
    transport = "streamable-http" if "--http" in sys.argv else "stdio"
    mcp.run(transport=transport)


if __name__ == "__main__":
    main()
