import pytest

from postgres_mcp.safety import UnsafeQueryError, apply_row_limit, validate_read_only


@pytest.mark.parametrize("sql", [
    "SELECT 1",
    "select * from calls where status = 'answered'",
    "WITH x AS (SELECT 1) SELECT * FROM x",
    "EXPLAIN SELECT * FROM calls",
    "SELECT 1; -- trailing comment",
    "/* lead */ SELECT 1",
])
def test_allows_read_only(sql):
    assert validate_read_only(sql)


@pytest.mark.parametrize("sql", [
    "DELETE FROM calls",
    "update calls set status='x'",
    "DROP TABLE calls",
    "SELECT 1; DROP TABLE calls",
    "SELECT 1; SELECT 2",
    "INSERT INTO calls VALUES (1)",
    "select * from calls; -- then\n delete from calls",
    "CREATE TABLE t (id int)",
    "",
])
def test_rejects_writes_and_multistatement(sql):
    with pytest.raises(UnsafeQueryError):
        validate_read_only(sql)


def test_row_limit_wraps_query():
    out = apply_row_limit("SELECT * FROM calls", 50)
    assert out.endswith("LIMIT 50")
    assert "SELECT * FROM calls" in out
