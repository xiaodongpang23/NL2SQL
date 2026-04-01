# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

NL2SQL financial dataset — a PostgreSQL schema and sample CSV data for a financial domain database, intended for NL2SQL model training, evaluation, or demonstration.

## Environment

- **Conda env**: `nl2sql` (Python 3.11) — activate with `conda activate nl2sql`
- **Packages**: psycopg2, pandas, sqlalchemy, jupyter, ipykernel, notebook
- **PostgreSQL**: cluster 14 on port 5433 (Unix socket, peer auth — no password)
- **Database**: `nl2sql` on port 5433, owned by `xpang`

## Database Setup

To (re)create the database schema and load all data from scratch:

```bash
conda activate nl2sql
python setup_db.py
```

`setup_db.py` is idempotent — it drops all tables and reloads from the CSVs every run.

Connection string used: `postgresql+psycopg2://xpang@/nl2sql?host=/var/run/postgresql&port=5433`

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

All tables have a redundant `id` integer column alongside the typed PK (artifact of pandas CSV export). Relationships between tables use matching `customer_id` / `investment_id` columns — only `transactions.account_id → accounts(account_id)` has an enforced `REFERENCES` constraint.

The `customer` CSV has multi-line quoted addresses, so its 100 records span ~200 physical lines.

## Chatbot Application

Three-file Python app — see `docs/superpowers/specs/2026-04-01-nl2sql-chatbot-design.md` for the full design.

| File | Role |
|---|---|
| `db.py` | `run_query(sql) -> list[dict]` — executes SELECT queries, 50-row truncation, SELECT-only guard |
| `agent.py` | `Agent` class — Claude tool-calling loop, conversation history, schema in system prompt |
| `chatbot.py` | Gradio `ChatInterface` — entry point, formats SQL + answer for display |

### Running

```bash
conda activate nl2sql
export ANTHROPIC_API_KEY=sk-ant-...
python chatbot.py
# Open http://127.0.0.1:7860
```

### Tests

```bash
# All tests (10 total)
pytest tests/ -v

# Single test file
pytest tests/test_db.py -v
pytest tests/test_agent.py -v
```

`tests/test_db.py` — hits the live database (PostgreSQL port 5433 must be running).
`tests/test_agent.py` — mocks the Anthropic client; no API key or DB required.
