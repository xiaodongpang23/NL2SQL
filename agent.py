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
