from sqlalchemy import create_engine, text

_DB_URL = "postgresql+psycopg2://xpang@/nl2sql?host=/var/run/postgresql&port=5433"
_engine = create_engine(_DB_URL)

_ROW_LIMIT = 50


def run_query(sql: str) -> list[dict]:
    """Execute a SELECT query and return rows as a list of dicts.

    Fetches all matching rows, then returns the first _ROW_LIMIT rows.
    If the result exceeds _ROW_LIMIT rows, appends {"_truncated": True, "_total": n}
    as the last element so the caller knows results were cut off.

    Raises ValueError if sql is not a SELECT statement.
    Raises on SQL errors.
    """
    if not sql.strip().upper().startswith("SELECT"):
        raise ValueError(f"Only SELECT queries are allowed, got: {sql[:50]!r}") # guard against destructive SQL

    with _engine.connect() as conn:
        result = conn.execute(text(sql))
        rows = [dict(row._mapping) for row in result]

    if len(rows) > _ROW_LIMIT:      # cap at 50 rows for performance and to avoid overwhelming the user
        total = len(rows)
        rows = rows[:_ROW_LIMIT]
        rows.append({"_truncated": True, "_total": total})

    return rows         # list of dicts → JSON-serialized back to Claude
