# postgres-mcp-server

A small, production-minded **Model Context Protocol (MCP) server** that gives LLM agents
**safe, read-only access to PostgreSQL**. Built with the official Python MCP SDK (`FastMCP`)
and `psycopg3`.

Use it from Claude Desktop, Cursor, Claude Code, or any MCP-compatible agent to let the
model explore a schema and answer questions over live data, without the ability to change it.

## Why

Agents are good at writing SQL and bad at knowing when not to. This server makes the
"not" part structural:

| Layer | Protection |
|---|---|
| **Database session** | every connection runs with `default_transaction_read_only=on` and a `statement_timeout` |
| **Query validation** | only a single `SELECT` / `WITH` / `EXPLAIN` is accepted; writes, DDL, and multi-statement input are rejected before reaching the DB |
| **Row cap** | results are wrapped in `LIMIT MAX_ROWS` so a careless `SELECT *` can't flood the context window |
| **Least privilege** | README and `sql/schema.sql` show how to create a read-only role; the server never needs more |
| **Errors as data** | DB errors return as JSON the agent can reason about, not stack traces |

## Tools

| Tool | What it does |
|---|---|
| `list_tables(schema="public")` | tables + approximate row counts |
| `describe_table(table, schema="public")` | columns, types, nullability |
| `run_query(sql)` | one read-only statement, capped at `MAX_ROWS` |
| `campaign_summary(campaign_id, days=7)` | example **domain tool**: KPIs for a voice-AI call campaign (answer rate, booking rate, avg duration, cost, latency) |

`campaign_summary` shows the pattern for turning a recurring analyst question into a typed
tool the agent can call directly, instead of guessing SQL every time.

## Quick start

```bash
git clone https://github.com/makkarss929/postgres-mcp-server
cd postgres-mcp-server
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

cp .env.example .env          # set DATABASE_URL to a READ-ONLY role
psql "$DATABASE_URL" -f sql/schema.sql   # optional sample schema
psql "$DATABASE_URL" -f sql/seed.sql     # optional sample data

pytest                        # safety tests
postgres-mcp                  # stdio server
```

Interactive inspector:

```bash
mcp dev src/postgres_mcp/server.py
```

## Connect to Claude Desktop / Cursor

Add to `claude_desktop_config.json` (or Cursor's MCP settings):

```json
{
  "mcpServers": {
    "postgres": {
      "command": "postgres-mcp",
      "env": {
        "DATABASE_URL": "postgresql://readonly_user:password@localhost:5432/nextdialog",
        "MAX_ROWS": "200"
      }
    }
  }
}
```

Then ask: *"Which campaign had the best booking rate this week, and what was its average latency?"*
The agent will call `list_tables` → `describe_table` → `run_query` (or `campaign_summary`) on its own.

## Remote / HTTP mode

```bash
postgres-mcp --http      # streamable HTTP on http://localhost:8000/mcp
```

## Project layout

```
src/postgres_mcp/
  server.py    # FastMCP app, tools, connection pool lifespan
  safety.py    # read-only validation + row cap (unit tested)
sql/
  schema.sql   # sample voice-AI calls schema + read-only role
  seed.sql     # sample data
tests/
  test_safety.py
```

## Ideas to extend

- Add tracing (Langfuse / OpenTelemetry) around each tool call: prompt, SQL, rows, latency, cost.
- Add a `explain_query` tool so the agent can check cost before running heavy queries.
- Add an allow-list of schemas/tables for multi-tenant deployments.
- Add a `run_query` eval set: natural-language question → expected SQL/result, to catch regressions.

## License

MIT © Tarun Makkar
