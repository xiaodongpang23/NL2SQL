import json
import os
import anthropic
from datetime import datetime
from pathlib import Path
from uuid import uuid4
from dotenv import load_dotenv
from db import run_query

load_dotenv()

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

VERIFY_SYSTEM_PROMPT = f"""You are a SQL verification assistant. Given a user's question and a generated \
SQL query, verify that the SQL correctly answers the question using the database schema below.

<schema>
{_DDL}
</schema>

Respond with EXACTLY one of:
APPROVED
REJECTED: <one-sentence explanation of what is wrong>

No other text."""

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

_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")
# Fall back to _MODEL if ANTHROPIC_VERIFY_MODEL is not set or invalid
_VERIFY_MODEL = os.getenv("ANTHROPIC_VERIFY_MODEL", _MODEL)
_MAX_TOOL_ITERATIONS = 3


def _conversations_dir(user: str, project: str) -> Path:
    d = Path(__file__).parent / "conversations" / user / project
    d.mkdir(parents=True, exist_ok=True)
    return d


class Agent:
    def __init__(self, user: str = "", project: str = "default", session_id: str | None = None):
        self._client = anthropic.Anthropic()
        self.history: list[dict] = []
        self.user = user
        self.project = project
        self.session_id = session_id or str(uuid4())
        self._created_at = datetime.now().isoformat()
        if user:
            d = _conversations_dir(user, project)
            self._session_path: Path | None = d / f"{self.session_id}.json"
        else:
            self._session_path = None  # anonymous — no persistence

    # ------------------------------------------------------------------
    # SQL verification
    # ------------------------------------------------------------------

    def _verify_sql(self, question: str, sql: str) -> tuple[bool, str]:
        """Ask a fast LLM to verify the SQL correctly answers the question.

        Falls back to the main model if the verify model is unavailable,
        and approves the query if both fail (so a misconfigured model never
        blocks legitimate queries).
        """
        payload = {
            "max_tokens": 128,
            "system": VERIFY_SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": f"User question: {question}\n\nGenerated SQL:\n{sql}"}],
        }
        for model in dict.fromkeys([_VERIFY_MODEL, _MODEL]):  # deduplicated, order preserved
            try:
                response = self._client.messages.create(model=model, **payload)
                text = response.content[0].text.strip()
                if text.upper().startswith("APPROVED"):
                    return True, text
                return False, text  # REJECTED: <reason>
            except Exception:
                continue  # try next model
        # If every model attempt failed, approve so the query can still run
        return True, "APPROVED (verification unavailable)"

    # ------------------------------------------------------------------
    # Session persistence
    # ------------------------------------------------------------------

    def _serialize_history(self) -> list[dict]:
        """Convert Anthropic SDK content blocks to plain dicts for JSON serialization."""
        result = []
        for msg in self.history:
            content = msg["content"]
            if isinstance(content, str):
                result.append({"role": msg["role"], "content": content})
            elif isinstance(content, list):
                blocks = []
                for block in content:
                    if isinstance(block, dict):
                        blocks.append(block)
                    elif hasattr(block, "type"):
                        if block.type == "text":
                            blocks.append({"type": "text", "text": block.text})
                        elif block.type == "tool_use":
                            blocks.append({
                                "type": "tool_use",
                                "id": block.id,
                                "name": block.name,
                                "input": dict(block.input),
                            })
                result.append({"role": msg["role"], "content": blocks})
        return result

    def _extract_turns(self) -> list[dict]:
        """Walk history and extract {user, assistant, sql} summaries for display."""
        turns = []
        i = 0
        while i < len(self.history):
            msg = self.history[i]
            if msg["role"] == "user" and isinstance(msg["content"], str):
                user_text = msg["content"]
                sql_list: list[str] = []
                answer = ""
                j = i + 1
                while j < len(self.history):
                    m = self.history[j]
                    if m["role"] == "user" and isinstance(m["content"], str):
                        break  # start of next user turn
                    if m["role"] == "assistant":
                        for block in m["content"]:
                            btype = (block.get("type") if isinstance(block, dict)
                                     else getattr(block, "type", None))
                            if btype == "tool_use":
                                inp = (block.get("input", {}) if isinstance(block, dict)
                                       else block.input)
                                sql = inp.get("sql", "")
                                if sql:
                                    sql_list.append(sql)
                            elif btype == "text":
                                answer = (block.get("text", "") if isinstance(block, dict)
                                          else block.text)
                    j += 1
                turns.append({
                    "user": user_text,
                    "assistant": answer,
                    "sql": "\n\n".join(sql_list) if sql_list else None,
                })
                i = j
            else:
                i += 1
        return turns

    def get_display_history(self) -> list[dict]:
        """Return turn summaries for reconstructing a Gradio chatbot display."""
        return self._extract_turns()

    def save(self) -> None:
        """Persist this session to disk. No-op for anonymous agents (user='')."""
        if not self._session_path:
            return
        # Preserve a user-set name across saves
        existing_name = ""
        if self._session_path.exists():
            try:
                existing_name = json.loads(self._session_path.read_text()).get("name", "")
            except Exception:
                pass
        preview = next(
            (m["content"] for m in self.history
             if m["role"] == "user" and isinstance(m["content"], str)),
            "",
        )
        data = {
            "id": self.session_id,
            "name": existing_name,
            "created_at": self._created_at,
            "updated_at": datetime.now().isoformat(),
            "preview": preview[:100],
            "turns": self._extract_turns(),
            "raw_history": self._serialize_history(),
        }
        self._session_path.write_text(json.dumps(data, indent=2, default=str))

    @classmethod
    def load(cls, user: str, project: str, session_id: str) -> "Agent":
        """Load a saved session from disk and restore full conversation history."""
        path = _conversations_dir(user, project) / f"{session_id}.json"
        data = json.loads(path.read_text())
        agent = cls(user=user, project=project, session_id=session_id)
        agent._created_at = data["created_at"]
        agent._session_path = path  # overwrite so save() reuses the same file
        agent.history = data["raw_history"]
        return agent

    @staticmethod
    def list_sessions(user: str, project: str) -> list[dict]:
        """List all saved sessions for a user/project, newest first."""
        d = Path(__file__).parent / "conversations" / user / project
        if not d.exists():
            return []
        sessions = []
        for f in d.glob("*.json"):
            try:
                data = json.loads(f.read_text())
                sessions.append({
                    "id": data["id"],
                    "name": data.get("name", ""),
                    "preview": data.get("preview", ""),
                    "updated_at": data.get("updated_at", ""),
                    "created_at": data.get("created_at", ""),
                })
            except Exception:
                continue
        return sorted(sessions, key=lambda s: s["updated_at"], reverse=True)

    @staticmethod
    def list_projects(user: str) -> list[str]:
        """List all project names for a user."""
        d = Path(__file__).parent / "conversations" / user
        if not d.exists():
            return []
        return sorted(p.name for p in d.iterdir() if p.is_dir())

    @staticmethod
    def create_project(user: str, project: str) -> None:
        """Create a project directory without starting a session."""
        _conversations_dir(user, project)

    @staticmethod
    def rename_session(user: str, project: str, session_id: str, new_name: str) -> None:
        """Update the display name of a session without touching history."""
        path = Path(__file__).parent / "conversations" / user / project / f"{session_id}.json"
        if not path.exists():
            return
        data = json.loads(path.read_text())
        data["name"] = new_name.strip()[:100]
        path.write_text(json.dumps(data, indent=2, default=str))

    @staticmethod
    def delete_session(user: str, project: str, session_id: str) -> None:
        """Permanently delete a session file."""
        path = Path(__file__).parent / "conversations" / user / project / f"{session_id}.json"
        if path.exists():
            path.unlink()

    # ------------------------------------------------------------------
    # Chat
    # ------------------------------------------------------------------

    def chat(self, user_message: str) -> tuple[str, str | None]:
        """Send a message and return (answer, sql_used).

        sql_used is None if Claude answered without querying the database.
        If multiple queries were run, sql_used contains all of them joined by newlines.
        Rolls back the user message from history if an API exception is raised,
        so the conversation state remains valid for subsequent calls.
        """
        self.history.append({"role": "user", "content": user_message})

        sql_calls: list[str] = []

        try:
            for _ in range(_MAX_TOOL_ITERATIONS):
                response = self._client.messages.create(
                    model=_MODEL,
                    max_tokens=4096,
                    system=SYSTEM_PROMPT,
                    tools=TOOLS,
                    messages=self.history,
                )

                if response.stop_reason != "tool_use":
                    answer = next(
                        (block.text for block in response.content if block.type == "text"),
                        "",
                    )
                    self.history.append({"role": "assistant", "content": response.content})
                    sql_used = "\n\n".join(sql_calls) if sql_calls else None
                    self.save()
                    return answer, sql_used  # Claude has a final answer

                # Append assistant turn so Claude sees the tool call it made
                self.history.append({"role": "assistant", "content": response.content})

                tool_results = []
                for block in response.content:
                    if block.type != "tool_use":
                        continue
                    sql = block.input["sql"]

                    # Verify SQL with a lightweight LLM review before executing
                    approved, feedback = self._verify_sql(user_message, sql)
                    if not approved:
                        content = f"SQL verification failed: {feedback}"
                    else:
                        sql_calls.append(sql)
                        try:
                            rows = run_query(sql)
                            content = json.dumps(rows, default=str)
                        except Exception as exc:
                            content = f"Error: {exc}"  # fed back to Claude to retry

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": content,
                    })

                self.history.append({"role": "user", "content": tool_results})
                # → loop back, call Claude again with the tool results

        except Exception:
            # Roll back the user message so history stays valid for future calls
            if self.history and self.history[-1] == {"role": "user", "content": user_message}:
                self.history.pop()
            raise

        # Exceeded max iterations
        sql_used = "\n\n".join(sql_calls) if sql_calls else None
        self.save()
        return "I was unable to complete this query.", sql_used
