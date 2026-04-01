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
    assert rows[-1]["_truncated"] is True
    assert rows[-1]["_total"] > 50


def test_run_query_no_truncation_under_limit():
    rows = run_query("SELECT * FROM loans LIMIT 10")
    assert len(rows) == 10
    assert "_truncated" not in rows[-1]


def test_run_query_raises_on_bad_sql():
    with pytest.raises(Exception):
        run_query("SELECT * FROM nonexistent_table_xyz")


def test_run_query_rejects_non_select():
    with pytest.raises(ValueError, match="Only SELECT queries are allowed"):
        run_query("DROP TABLE customer")
