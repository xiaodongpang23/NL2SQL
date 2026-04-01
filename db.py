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
