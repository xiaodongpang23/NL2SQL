# NL2SQL Financial Chatbot — Design Spec

**Date:** 2026-04-01  
**Status:** Approved

---

## Overview

A browser-based chatbot that lets users ask natural language questions about the financial database and receive answers backed by live SQL queries. The interface shows both the generated SQL and a plain-language answer for each question.

**Stack:** Python 3.11 (conda env `nl2sql`), Gradio 5, Claude API (`claude-sonnet-4-6`), PostgreSQL 14 (port 5433).

---

## Architecture

Three modules with clear boundaries:

| File | Responsibility |
|---|---|
| `db.py` | Database connection and SQL execution |
| `agent.py` | Claude API agent — prompt, tool-calling, conversation history |
| `chatbot.py` | Gradio UI — entry point, response formatting |

### `db.py`

- Creates a SQLAlchemy engine using the existing connection string:  
  `postgresql+psycopg2://xpang@/nl2sql?host=/var/run/postgresql&port=5433`
- Exposes one function: `run_query(sql: str) -> list[dict]`
- Returns rows as a list of dicts (column name → value)
- Truncates results to **50 rows** if the result set is larger, appending a metadata entry `{"_truncated": True, "_total": n}` so the agent can mention this to the user
- Raises exceptions on SQL errors (caught by `agent.py`)

### `agent.py`

- Initializes the Anthropic client and holds the **system prompt** (hardcoded at module load, not per-request)
- System prompt contains: the full schema DDL, instructions to answer only from the database, and the tool spec
- Defines one Claude tool: `execute_sql(sql: str)` — description makes clear it is for SELECT queries only
- `Agent` class with:
  - `history: list` — conversation messages (persisted across turns within a session)
  - `chat(user_message: str) -> tuple[str, str | None]` — returns `(answer, sql_used)`. `sql_used` is `None` if Claude answered without querying (e.g. off-topic question)
- **Tool-call loop:** after receiving a tool call from Claude, execute the SQL via `db.py`, append the result as a tool result message, and continue the API call. Repeat up to **3 times** per user message (for multi-step queries). If SQL raises an exception, feed the error string back as the tool result so Claude can retry or explain.
- Conversation history is stored in-memory (a Python list on the `Agent` instance) — no persistence across process restarts

### `chatbot.py`

- Instantiates one `Agent` (shared across the Gradio session)
- Defines a `respond(message, history)` function for Gradio's `ChatInterface`
- **Ignores Gradio's `history` parameter** — uses `Agent.history` instead, which contains the full tool-call/result messages that Gradio never sees. Gradio's history is display-only.
- Formats the response: if `sql_used` is not None, prepends a fenced SQL code block before the answer
- Launches `gr.ChatInterface` on `http://localhost:7860`

---

## Data Flow

```
User types question
       │
       ▼
chatbot.py: respond(message, history)
       │
       ▼
agent.py: Agent.chat(user_message)
  - appends user message to history
  - calls Claude API with system prompt + history
       │
       ├── Claude calls execute_sql(sql)
       │       │
       │       ▼
       │   db.py: run_query(sql) → rows (max 50) or error string
       │       │
       │       ▼
       │   result appended to history as tool result
       │   Claude API called again (loop, max 3 iterations)
       │
       ▼
Claude returns final text answer
       │
       ▼
chatbot.py formats:
  ````sql
  SELECT ...
  ````
  Natural language answer...
       │
       ▼
Gradio renders in chat window
```

---

## System Prompt

```
You are a helpful assistant that answers questions about a financial database.
You have access to a PostgreSQL database with the following schema:

<schema>
[full DDL from DDL-create-financial-tables.sql]
</schema>

To answer questions, use the execute_sql tool to run SELECT queries.
Only use SELECT statements — never INSERT, UPDATE, DELETE, or DDL.
If a question cannot be answered from the database, say so clearly.
If query results are truncated, mention that only the first 50 rows are shown.
Always explain the results in plain language after showing any data.
```

---

## Error Handling

| Scenario | Behavior |
|---|---|
| SQL syntax error | Error message fed back to Claude as tool result; Claude retries or explains |
| SQL runtime error (e.g. FK violation on a bad query) | Same as above |
| Truncated results (>50 rows) | `_truncated` flag in results; Claude mentions truncation in its answer |
| Off-topic question | Claude answers without calling the tool; no SQL shown |
| Claude tool loop exceeds 3 iterations | Return Claude's last response as-is |

---

## Display Format

Each assistant message is a single chat bubble containing:

````
```sql
SELECT customer_id, name, age FROM customer WHERE age > 60 ORDER BY age DESC
```

Found **23 customers** over age 60. The oldest is Margaret Chen at age 84,
followed by Robert Torres at 81. Most are concentrated in the 60–70 age range.
````

If Claude answers without querying (off-topic or clarification), only the plain text is shown — no SQL block.

---

## Files to Create

```
NL2SQL/
├── db.py
├── agent.py
├── chatbot.py
└── docs/superpowers/specs/2026-04-01-nl2sql-chatbot-design.md  ← this file
```

`setup_db.py` and the existing data files are unchanged.

---

## Running the App

```bash
conda activate nl2sql
pip install gradio anthropic  # if not already installed
python chatbot.py
# Open http://localhost:7860
```

A `ANTHROPIC_API_KEY` environment variable must be set.

---

## Out of Scope

- User authentication
- Persistent chat history across sessions
- Non-SELECT query support (writes, schema changes)
- Deployment beyond localhost
