# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

NL2SQL financial dataset — a PostgreSQL schema, sample CSV data, and a browser-based chatbot that answers natural language questions about the data using the Claude API.

## Environment

- **Conda env**: `nl2sql` (Python 3.11) — activate with `conda activate nl2sql`
- **Key packages**: psycopg2, sqlalchemy, pandas, anthropic, gradio, python-dotenv, jupyter, pytest
- **PostgreSQL**: cluster 14 on port 5433 (Unix socket, peer auth — no password)
- **Database**: `nl2sql` on port 5433, owned by `xpang`
- **Config**: copy `.env.example` → `.env` and fill in `ANTHROPIC_API_KEY` and optionally `ANTHROPIC_MODEL`

## Database Setup

To (re)create the schema and load all data from scratch (idempotent):

```bash
conda activate nl2sql
python setup_db.py
```

Connection string: `postgresql+psycopg2://xpang@/nl2sql?host=/var/run/postgresql&port=5433`

## Database Schema

Six tables in a financial domain:

| Table | PK | Row Count |
|---|---|---|
| `customer` | `customer_id` | 100 |
| `accounts` | `account_id` | 200 |
| `investments` | `investment_id` | 150 |
| `loans` | `loan_id` | 100 |
| `orders` | `order_id` | 300 |
| `transactions` | `transaction_id` | 500 |

All tables have a redundant `id` integer column alongside the typed PK (artifact of pandas CSV export). Cross-table relationships use matching `customer_id` / `investment_id` columns — only `transactions.account_id → accounts(account_id)` has an enforced `REFERENCES` constraint.

The `customer` CSV has multi-line quoted addresses, so its 100 records span ~200 physical lines.

## Chatbot Application

Three-file Python app — full design in `docs/superpowers/specs/2026-04-01-nl2sql-chatbot-design.md`.

| File | Role |
|---|---|
| `db.py` | `run_query(sql) -> list[dict]` — SELECT-only guard, executes query, 50-row truncation with `{"_truncated": True, "_total": n}` sentinel |
| `agent.py` | `Agent` class — loads `.env`, embeds schema DDL in system prompt, Claude tool-calling loop (max 3 iterations), in-memory conversation history, rolls back history on API exception |
| `chatbot.py` | Gradio `ChatInterface` — ignores Gradio's history param (uses `Agent.history`), formats response as fenced SQL block + plain-language answer |

### Running

```bash
conda activate nl2sql
# Edit .env with your ANTHROPIC_API_KEY first
python chatbot.py
# Open http://127.0.0.1:7860
```

### Tests

```bash
# All tests (10 total)
conda activate nl2sql && pytest tests/ -v

# Single test
pytest tests/test_db.py::test_run_query_truncates_at_50_rows -v
```

`tests/test_db.py` — hits the live database (port 5433 must be running).
`tests/test_agent.py` — mocks the Anthropic client; no API key or DB required.
