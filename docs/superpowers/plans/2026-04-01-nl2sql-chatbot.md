# NL2SQL Financial Chatbot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a browser-based chatbot that translates natural language questions into SQL queries against the financial PostgreSQL database and displays both the SQL and a plain-language answer.

**Architecture:** Three focused Python modules — `db.py` executes SQL, `agent.py` drives Claude via tool-calling to generate and run queries, and `chatbot.py` wraps everything in a Gradio `ChatInterface`. Conversation history lives in-memory on the `Agent` instance; Gradio's own history is ignored in favour of it.

**Tech Stack:** Python 3.11, `anthropic` SDK, `gradio>=5`, `sqlalchemy`, `psycopg2`, `pytest`

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `db.py` | Create | SQLAlchemy engine, `run_query(sql) -> list[dict]`, 50-row truncation |
| `agent.py` | Create | `Agent` class: system prompt with schema, tool-calling loop, history |
| `chatbot.py` | Create | Gradio `ChatInterface`, response formatting |
| `tests/__init__.py` | Create | Make tests a package |
| `tests/test_db.py` | Create | Unit tests for `db.py` against live DB |
| `tests/test_agent.py` | Create | Unit tests for `agent.py` with mocked Anthropic client |

---

## Task 1: Install Dependencies

**Files:**
- No files created

- [ ] **Step 1: Install `gradio` and `anthropic` into the conda env**

```bash
conda activate nl2sql
pip install "gradio>=5" anthropic
```

- [ ] **Step 2: Verify imports work**

```bash
python -c "import gradio, anthropic; print('gradio', gradio.__version__, '| anthropic', anthropic.__version__)"
```

Expected: both version strings print without error.

- [ ] **Step 3: Confirm `ANTHROPIC_API_KEY` is available**

```bash
python -c "import os, anthropic; c = anthropic.Anthropic(); print('API key OK')"
```

Expected: `API key OK`. If it prints an `AuthenticationError`, export your key:
```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

---

## Task 2: `db.py` — SQL Execution Module

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/test_db.py`
- Create: `db.py`

- [ ] **Step 1: Create the tests package**

```bash
mkdir -p tests && touch tests/__init__.py
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_db.py`:

```python
import pytest
from db import run_query


def test_run_query_returns_list_of_dicts():
    rows = run_query("SELECT customer_id, name FROM customer LIMIT 3")
    assert isinstance(rows, list)
    assert len(rows) == 3
    assert "customer_id" in rows[0]
    assert "name" in rows[0]


def test_run_query_truncates_at_50_rows():
    # transactions has 500 rows — well over the 50-row limit
    rows = run_query("SELECT * FROM transactions")
    assert len(rows) == 51  # 50 data rows + 1 truncation metadata dict
    assert rows[-1] == {"_truncated": True, "_total": 500}


def test_run_query_no_truncation_under_limit():
    rows = run_query("SELECT * FROM loans LIMIT 10")
    assert len(rows) == 10
    assert "_truncated" not in rows[-1]


def test_run_query_raises_on_bad_sql():
    with pytest.raises(Exception):
        run_query("SELECT * FROM nonexistent_table_xyz")
```

- [ ] **Step 3: Run tests to confirm they fail (db.py doesn't exist yet)**

```bash
conda activate nl2sql && cd /home/xpang/Projects/NL2SQL
pytest tests/test_db.py -v
```

Expected: `ModuleNotFoundError: No module named 'db'`

- [ ] **Step 4: Implement `db.py`**

Create `db.py`:

```python
from sqlalchemy import create_engine, text

_DB_URL = "postgresql+psycopg2://xpang@/nl2sql?host=/var/run/postgresql&port=5433"
_engine = create_engine(_DB_URL)

_ROW_LIMIT = 50


def run_query(sql: str) -> list[dict]:
    """Execute a SELECT query and return rows as a list of dicts.

    If the result set exceeds _ROW_LIMIT rows, returns the first _ROW_LIMIT rows
    followed by {"_truncated": True, "_total": <total_count>}.
    Raises on SQL errors.
    """
    with _engine.connect() as conn:
        result = conn.execute(text(sql))
        rows = [dict(row._mapping) for row in result]

    if len(rows) > _ROW_LIMIT:
        total = len(rows)
        rows = rows[:_ROW_LIMIT]
        rows.append({"_truncated": True, "_total": total})

    return rows
```

- [ ] **Step 5: Run tests to confirm they pass**

```bash
pytest tests/test_db.py -v
```

Expected:
```
tests/test_db.py::test_run_query_returns_list_of_dicts PASSED
tests/test_db.py::test_run_query_truncates_at_50_rows PASSED
tests/test_db.py::test_run_query_no_truncation_under_limit PASSED
tests/test_db.py::test_run_query_raises_on_bad_sql PASSED
```

- [ ] **Step 6: Commit**

```bash
git add db.py tests/__init__.py tests/test_db.py
git commit -m "feat: add db.py SQL execution module with 50-row truncation"
```

---

## Task 3: `agent.py` — Claude Agent with Tool-Calling

**Files:**
- Create: `tests/test_agent.py`
- Create: `agent.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_agent.py`:

```python
import json
import pytest
from unittest.mock import MagicMock, patch, call


def _make_text_response(text: str):
    """Build a mock Anthropic response that returns a plain text answer."""
    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = text

    response = MagicMock()
    response.stop_reason = "end_turn"
    response.content = [text_block]
    return response


def _make_tool_response(tool_id: str, sql: str):
    """Build a mock Anthropic response that calls execute_sql."""
    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.id = tool_id
    tool_block.name = "execute_sql"
    tool_block.input = {"sql": sql}

    response = MagicMock()
    response.stop_reason = "tool_use"
    response.content = [tool_block]
    return response


@patch("agent.anthropic.Anthropic")
def test_chat_no_tool_call_returns_answer_and_none_sql(mock_cls):
    from agent import Agent

    mock_client = MagicMock()
    mock_cls.return_value = mock_client
    mock_client.messages.create.return_value = _make_text_response("I can only answer database questions.")

    agent = Agent()
    answer, sql = agent.chat("What is the weather?")

    assert isinstance(answer, str)
    assert len(answer) > 0
    assert sql is None


@patch("agent.anthropic.Anthropic")
@patch("agent.run_query")
def test_chat_tool_call_returns_answer_and_sql(mock_run_query, mock_cls):
    from agent import Agent

    mock_client = MagicMock()
    mock_cls.return_value = mock_client
    mock_run_query.return_value = [{"count": 100}]

    mock_client.messages.create.side_effect = [
        _make_tool_response("tool_abc", "SELECT COUNT(*) FROM customer"),
        _make_text_response("There are 100 customers."),
    ]

    agent = Agent()
    answer, sql = agent.chat("How many customers are there?")

    assert answer == "There are 100 customers."
    assert sql == "SELECT COUNT(*) FROM customer"
    mock_run_query.assert_called_once_with("SELECT COUNT(*) FROM customer")


@patch("agent.anthropic.Anthropic")
@patch("agent.run_query")
def test_chat_history_accumulates_across_turns(mock_run_query, mock_cls):
    from agent import Agent

    mock_client = MagicMock()
    mock_cls.return_value = mock_client
    mock_run_query.return_value = [{"count": 5}]

    mock_client.messages.create.side_effect = [
        _make_tool_response("t1", "SELECT COUNT(*) FROM loans"),
        _make_text_response("There are 5 loans."),
        _make_text_response("The total is 5."),
    ]

    agent = Agent()
    agent.chat("How many loans?")
    agent.chat("What was that total again?")

    # Second API call should include history from the first turn
    second_call_messages = mock_client.messages.create.call_args_list[2][1]["messages"]
    roles = [m["role"] for m in second_call_messages]
    assert roles.count("user") >= 2  # original question + tool result + second question
    assert roles.count("assistant") >= 1


@patch("agent.anthropic.Anthropic")
@patch("agent.run_query")
def test_chat_sql_error_is_fed_back_to_claude(mock_run_query, mock_cls):
    from agent import Agent

    mock_client = MagicMock()
    mock_cls.return_value = mock_client
    mock_run_query.side_effect = Exception("relation does not exist")

    mock_client.messages.create.side_effect = [
        _make_tool_response("t1", "SELECT * FROM bad_table"),
        _make_text_response("I couldn't find that table."),
    ]

    agent = Agent()
    answer, sql = agent.chat("Query a bad table")

    # Claude should have been called twice: once for tool call, once after error
    assert mock_client.messages.create.call_count == 2
    # The tool result message in the second call should contain the error
    second_call_messages = mock_client.messages.create.call_args_list[1][1]["messages"]
    tool_result_msg = next(
        m for m in second_call_messages
        if m["role"] == "user"
        and isinstance(m["content"], list)
        and m["content"][0].get("type") == "tool_result"
    )
    assert "relation does not exist" in tool_result_msg["content"][0]["content"]
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_agent.py -v
```

Expected: `ModuleNotFoundError: No module named 'agent'`

- [ ] **Step 3: Implement `agent.py`**

Create `agent.py`:

```python
import json
import anthropic
from pathlib import Path
from db import run_query

_DDL = (Path(__file__).parent / "DDL-create-financial-tables.sql").read_text()

SYSTEM_PROMPT = f"""You are a helpful assistant that answers questions about a financial database.
You have access to a PostgreSQL database with the following schema:

<schema>
{_DDL}
</schema>

To answer questions, use the execute_sql tool to run SELECT queries.
Only use SELECT statements — never INSERT, UPDATE, DELETE, or DDL.
If a question cannot be answered from the database, say so clearly.
If query results are truncated (you will see _truncated: true), mention that only the first 50 rows are shown.
Always explain the results in plain language after showing any data."""

TOOLS = [
    {
        "name": "execute_sql",
        "description": (
            "Execute a SELECT SQL query against the financial PostgreSQL database. "
            "Only use SELECT statements. Returns rows as a JSON array of objects."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "sql": {"type": "string", "description": "The SELECT SQL query to execute"}
            },
            "required": ["sql"],
        },
    }
]

_MODEL = "claude-sonnet-4-6"
_MAX_TOOL_ITERATIONS = 3


class Agent:
    def __init__(self):
        self._client = anthropic.Anthropic()
        self.history: list[dict] = []

    def chat(self, user_message: str) -> tuple[str, str | None]:
        """Send a message and return (answer, sql_used).

        sql_used is None if Claude answered without querying the database.
        If multiple queries were run, sql_used contains all of them joined by newlines.
        """
        self.history.append({"role": "user", "content": user_message})

        sql_calls: list[str] = []

        for _ in range(_MAX_TOOL_ITERATIONS):
            response = self._client.messages.create(
                model=_MODEL,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                messages=self.history,
            )

            if response.stop_reason != "tool_use":
                # Final answer — extract text and return
                answer = next(
                    (block.text for block in response.content if block.type == "text"),
                    "",
                )
                self.history.append({"role": "assistant", "content": response.content})
                sql_used = "\n\n".join(sql_calls) if sql_calls else None
                return answer, sql_used

            # Handle tool call
            self.history.append({"role": "assistant", "content": response.content})

            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                sql = block.input["sql"]
                sql_calls.append(sql)
                try:
                    rows = run_query(sql)
                    content = json.dumps(rows, default=str)
                except Exception as exc:
                    content = f"Error: {exc}"

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": content,
                })

            self.history.append({"role": "user", "content": tool_results})

        # Exceeded max iterations — return whatever text we have
        last_text = next(
            (block.text for block in response.content if block.type == "text"),
            "I was unable to complete this query.",
        )
        sql_used = "\n\n".join(sql_calls) if sql_calls else None
        return last_text, sql_used
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/test_agent.py -v
```

Expected:
```
tests/test_agent.py::test_chat_no_tool_call_returns_answer_and_none_sql PASSED
tests/test_agent.py::test_chat_tool_call_returns_answer_and_sql PASSED
tests/test_agent.py::test_chat_history_accumulates_across_turns PASSED
tests/test_agent.py::test_chat_sql_error_is_fed_back_to_claude PASSED
```

- [ ] **Step 5: Run the full test suite to make sure nothing broke**

```bash
pytest tests/ -v
```

Expected: all 8 tests pass.

- [ ] **Step 6: Commit**

```bash
git add agent.py tests/test_agent.py
git commit -m "feat: add Claude agent with tool-calling SQL loop"
```

---

## Task 4: `chatbot.py` — Gradio UI

**Files:**
- Create: `chatbot.py`

- [ ] **Step 1: Implement `chatbot.py`**

Create `chatbot.py`:

```python
import gradio as gr
from agent import Agent

_agent = Agent()


def respond(message: str, history: list) -> str:
    """Gradio callback. Ignores `history` — Agent maintains its own full history."""
    answer, sql_used = _agent.chat(message)
    if sql_used:
        return f"```sql\n{sql_used}\n```\n\n{answer}"
    return answer


demo = gr.ChatInterface(
    fn=respond,
    title="Financial Database Chatbot",
    description="Ask questions about customers, accounts, loans, investments, orders, and transactions.",
    examples=[
        "How many customers are there?",
        "What are the top 5 largest account balances?",
        "Which customers have both a loan and an investment?",
        "Show me the most recent 5 transactions.",
    ],
)

if __name__ == "__main__":
    demo.launch()
```

- [ ] **Step 2: Launch the app and do a smoke test**

```bash
conda activate nl2sql
cd /home/xpang/Projects/NL2SQL
python chatbot.py
```

Expected output:
```
Running on local URL:  http://127.0.0.1:7860
```

Open `http://127.0.0.1:7860` in a browser. Try: *"How many customers are there?"*

Expected response: a SQL code block followed by a plain-language answer like "There are 100 customers in the database."

- [ ] **Step 3: Test a follow-up question (multi-turn)**

In the same chat session, ask: *"Show me the 3 oldest ones."*

Expected: Claude uses context from the previous turn to know "ones" refers to customers, runs a query with `ORDER BY age DESC LIMIT 3`, and returns the result.

- [ ] **Step 4: Test an off-topic question**

Ask: *"What is the capital of France?"*

Expected: A plain text response with no SQL code block.

- [ ] **Step 5: Commit**

```bash
git add chatbot.py
git commit -m "feat: add Gradio chatbot UI"
```

---

## Task 5: Update `CLAUDE.md`

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Add the chatbot section to `CLAUDE.md`**

Append to `/home/xpang/Projects/NL2SQL/CLAUDE.md`:

```markdown

## Chatbot Application

Three-file Python app (`db.py`, `agent.py`, `chatbot.py`) — see `docs/superpowers/specs/2026-04-01-nl2sql-chatbot-design.md` for the full design.

### Running

```bash
conda activate nl2sql
export ANTHROPIC_API_KEY=sk-ant-...
python chatbot.py
# Open http://localhost:7860
```

### Tests

```bash
# All tests
pytest tests/ -v

# Single test
pytest tests/test_db.py::test_run_query_truncates_at_50_rows -v
```

`tests/test_db.py` hits the live database (port 5433 must be running).  
`tests/test_agent.py` mocks the Anthropic client — no API key required.
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md with chatbot run/test instructions"
```

---

## Verification

End-to-end check after all tasks complete:

```bash
conda activate nl2sql
cd /home/xpang/Projects/NL2SQL
pytest tests/ -v                   # 8 tests, all green
python chatbot.py                  # launches on :7860
```

In the browser, verify:
1. Simple count query shows SQL + answer
2. Multi-turn: follow-up question uses context from previous turn
3. Off-topic question returns plain text with no SQL block
4. Large result query (e.g. "List all transactions") mentions truncation
