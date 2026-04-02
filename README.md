# NL2SQL

A browser-based chatbot that answers natural language questions about a financial PostgreSQL database using the Claude API. Ask a question, get back the generated SQL and a plain-language answer.

## Quick Start

```bash
conda activate nl2sql
cp .env.example .env        # add your ANTHROPIC_API_KEY
python chatbot.py
# Open http://127.0.0.1:7860
```

To reset the database from the CSV files:

```bash
python setup_db.py
```

## Request → Answer Workflow

### 1. User types a question in the browser

`chatbot.py` receives it via Gradio's `ChatInterface`:

```python
def respond(message: str, history: list) -> str:
    answer, sql_used = _agent.chat(message)   # ← delegates to Agent
    if sql_used is not None:
        return f"```sql\n{sql_used}\n```\n\n{answer}"
    return answer
```

Gradio's `history` is **ignored** — `Agent` maintains its own full history (which includes tool-call/result turns that Gradio never sees).

---

### 2. Agent appends the message and calls Claude

`agent.py` — `Agent.chat()`:

```python
self.history.append({"role": "user", "content": user_message})

response = self._client.messages.create(
    model=_MODEL,                # from .env: ANTHROPIC_MODEL
    max_tokens=4096,
    system=SYSTEM_PROMPT,        # full DDL schema embedded here
    tools=TOOLS,                 # declares execute_sql tool
    messages=self.history,
)
```

The **system prompt** includes the full DDL so Claude knows all 6 tables and their columns. The **`execute_sql` tool definition** tells Claude it can run SELECT queries.

---

### 3. Claude decides to call the SQL tool

If Claude needs data, it returns `stop_reason == "tool_use"`. The loop handles it:

```python
for _ in range(_MAX_TOOL_ITERATIONS):   # max 3 rounds
    response = self._client.messages.create(...)

    if response.stop_reason != "tool_use":
        break                            # Claude has a final answer

    # Extract the SQL Claude wants to run
    for block in response.content:
        if block.type != "tool_use":
            continue
        sql = block.input["sql"]         # e.g. "SELECT COUNT(*) FROM customer"
        sql_calls.append(sql)

        try:
            rows = run_query(sql)
            content = json.dumps(rows, default=str)
        except Exception as exc:
            content = f"Error: {exc}"    # error fed back to Claude to retry

        tool_results.append({
            "type": "tool_result",
            "tool_use_id": block.id,
            "content": content,
        })

    # Append both sides to history so Claude sees the result of its tool use
    self.history.append({"role": "assistant", "content": response.content})
    self.history.append({"role": "user",      "content": tool_results})
    # → loop back, call Claude again with the results
```

---

### 4. `db.py` executes the SQL

```python
def run_query(sql: str) -> list[dict]:
    if not sql.strip().upper().startswith("SELECT"):
        raise ValueError(...)           # guard against destructive SQL

    with _engine.connect() as conn:
        result = conn.execute(text(sql))
        rows = [dict(row._mapping) for row in result]

    if len(rows) > _ROW_LIMIT:          # cap at 50 rows
        total = len(rows)
        rows = rows[:_ROW_LIMIT]
        rows.append({"_truncated": True, "_total": total})

    return rows                         # list of dicts → JSON-serialized back to Claude
```

---

### 5. Claude formulates the final answer

After receiving the query results as a tool result message, Claude returns `stop_reason == "end_turn"` with a plain-language answer. The agent extracts it and returns:

```python
answer = next(
    (block.text for block in response.content if block.type == "text"), ""
)
sql_used = "\n\n".join(sql_calls) if sql_calls else None
return answer, sql_used
```

---

### Full picture

```
Browser input
    │
    ▼
chatbot.py: respond(message, history)
    │
    ▼
agent.py: Agent.chat(message)
    ├─ append user message to history
    ├─ call Claude API (system prompt has full schema)
    │
    │   ┌─── Claude returns tool_use ────────────────────┐
    │   │                                                 │
    │   ▼                                                 │
    │  db.py: run_query(sql)                              │
    │   ├─ SELECT guard                                   │
    │   ├─ execute via SQLAlchemy → PostgreSQL port 5433  │
    │   └─ truncate at 50 rows if needed                  │
    │                                                     │
    │   result appended to history → call Claude again ──┘
    │   (up to 3 iterations)
    │
    ├─ Claude returns end_turn → extract text answer
    └─ return (answer, sql_used)
    │
    ▼
chatbot.py: format as ```sql block``` + answer
    │
    ▼
Gradio renders in browser
```

**Key design decisions:**
- Claude drives SQL generation via tool-calling — no regex parsing of SQL from text
- History includes every tool-call/result round-trip, giving Claude full context for follow-ups
- Errors from `db.py` are returned as tool results (not exceptions), letting Claude retry with corrected SQL

## Database Schema

| Table | PK | Rows |
|---|---|---|
| `customer` | `customer_id` | 100 |
| `accounts` | `account_id` | 200 |
| `investments` | `investment_id` | 150 |
| `loans` | `loan_id` | 100 |
| `orders` | `order_id` | 300 |
| `transactions` | `transaction_id` | 500 |

Only `transactions.account_id → accounts(account_id)` has an enforced FK constraint. All other relationships use matching `customer_id` / `investment_id` columns.

## Tests

```bash
pytest tests/ -v
```
