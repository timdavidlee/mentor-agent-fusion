"""Tests for `query_engine`, using tiny Parquet fixtures written here (no generator run)."""

import datetime as dt
from pathlib import Path
from typing import Any

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from query_engine import QueryEngine, ReadOnlyError, connect, load_schema

SCHEMA = load_schema()


def _write_table(directory: Path, table: str, rows: list[dict[str, Any]]) -> None:
    """Write `rows` with every schema column present; unspecified columns are null."""
    columns = [c.name for c in SCHEMA[table].columns]
    data = {name: [row.get(name) for row in rows] for name in columns}
    pq.write_table(pa.table(data), directory / f"{table}.parquet")


@pytest.fixture
def generated(tmp_path: Path) -> Path:
    root = tmp_path / "generated"
    visible = root / "seen" / "visible"
    hidden = root / "seen" / "hidden"
    (hidden / "truth").mkdir(parents=True)
    visible.mkdir(parents=True)
    (root / "held_out" / "visible").mkdir(parents=True)

    _write_table(
        visible,
        "tenant",
        [
            {
                "tenant_id": 1,
                "tenant_code": "T1",
                "name": "Alpha",
                "as_of_date": dt.date(2026, 6, 30),
            },
            {
                "tenant_id": 2,
                "tenant_code": "T2",
                "name": "Bravo",
                "as_of_date": dt.date(2026, 6, 30),
            },
        ],
    )
    _write_table(
        visible,
        "customer",
        [
            {"tenant_id": 1, "customer_id": 10, "account_number": "A1", "name": "Ann's Farm"},
            {"tenant_id": 1, "customer_id": 11, "account_number": "A2", "name": "Acme"},
            {"tenant_id": 2, "customer_id": 20, "account_number": "B1", "name": "Bob"},
        ],
    )
    pq.write_table(pa.table({"tenant_id": [1], "customer_id": [10], "value": [True]}),
                   hidden / "truth" / "active_customer.parquet")  # fmt: skip
    (hidden / "questions.jsonl").write_text('{"question_id": "q1", "answer": 42}\n')
    return root


@pytest.fixture
def engine(generated: Path):
    with QueryEngine("seen", tenant_id=1, generated_dir=generated) as eng:
        yield eng


def _files(root: Path) -> set[Path]:
    return {p for p in root.rglob("*") if p.is_file()}


# --- schema --------------------------------------------------------------------------


def test_schema_has_17_tables_all_with_tenant_id():
    assert len(SCHEMA) == 17
    for table in SCHEMA.values():
        assert "tenant_id" in [c.name for c in table.columns], table.name


# --- views, comments, helpers --------------------------------------------------------


def test_list_tables_matches_schema(engine: QueryEngine):
    assert engine.list_tables() == sorted(SCHEMA)


def test_describe_carries_schema_types_and_comments(engine: QueryEngine):
    cols = {c.name: c for c in engine.describe("customer")}
    assert list(cols) == [c.name for c in SCHEMA["customer"].columns]
    assert cols["customer_type"].comment == (
        "contractor, farm, government, manufacturer, individual"
    )
    assert cols["credit_limit"].type == "DECIMAL(12,2)"
    assert cols["name"].type == "VARCHAR"
    assert cols["address_line"].comment is None


def test_describe_unknown_table(engine: QueryEngine):
    with pytest.raises(KeyError):
        engine.describe("nope")


def test_missing_parquet_is_empty_typed_view(engine: QueryEngine):
    assert engine.run_sql("SELECT count(*) FROM invoice").rows == [(0,)]
    assert engine.describe("invoice")[0].name == "tenant_id"


def test_run_sql_returns_columns_and_rows(engine: QueryEngine):
    result = engine.run_sql("SELECT customer_id, name FROM customer ORDER BY customer_id")
    assert result.columns == ["customer_id", "name"]
    assert result.rows == [(10, "Ann's Farm"), (11, "Acme")]
    assert not result.truncated


def test_run_sql_truncates(engine: QueryEngine):
    result = engine.run_sql("SELECT * FROM range(5)", max_rows=2)
    assert len(result.rows) == 2 and result.truncated


def test_read_only_forms_allowed(engine: QueryEngine):
    engine.run_sql("EXPLAIN SELECT * FROM customer")
    engine.run_sql("WITH c AS (SELECT * FROM customer) SELECT count(*) FROM c")
    engine.run_sql("FROM tenant")


def test_empty_split_and_unknown_split(generated: Path):
    with QueryEngine("held_out", tenant_id=1, generated_dir=generated) as eng:
        assert eng.run_sql("SELECT count(*) FROM customer").rows == [(0,)]
    with pytest.raises(ValueError):
        connect("train", generated_dir=generated)  # type: ignore[arg-type]
    with pytest.raises(FileNotFoundError):
        connect("seen", generated_dir=generated / "missing")


# --- tenant scoping ------------------------------------------------------------------


def test_scoped_views_show_one_tenant(engine: QueryEngine):
    assert engine.run_sql("SELECT DISTINCT tenant_id FROM customer").rows == [(1,)]
    assert engine.run_sql("SELECT tenant_code FROM tenant").rows == [("T1",)]


def test_scoped_source_tables_hold_one_tenant(engine: QueryEngine):
    assert engine.run_sql("SELECT DISTINCT tenant_id FROM src.customer").rows == [(1,)]


def test_scoped_cannot_read_visible_parquet_directly(engine: QueryEngine, generated: Path):
    path = generated / "seen" / "visible" / "customer.parquet"
    with pytest.raises(duckdb.PermissionException):
        engine.run_sql(f"SELECT * FROM read_parquet('{path}')")


def test_unscoped_connect_sees_all_tenants(generated: Path):
    con = connect("seen", generated_dir=generated)
    assert con.execute("SELECT count(DISTINCT tenant_id) FROM customer").fetchall() == [(2,)]
    con.close()


# --- hidden/ is unreachable ----------------------------------------------------------


def _hidden_reads(generated: Path) -> list[str]:
    hidden = generated / "seen" / "hidden"
    visible = generated / "seen" / "visible"
    truth = hidden / "truth" / "active_customer.parquet"
    questions = hidden / "questions.jsonl"
    return [
        f"SELECT * FROM read_parquet('{truth}')",
        f"SELECT * FROM read_parquet('{visible}/../hidden/truth/active_customer.parquet')",
        f"SELECT * FROM read_json('{questions}')",
        f"SELECT * FROM read_text('{questions}')",
        f"SELECT * FROM read_csv('{questions}')",
        f"SELECT * FROM glob('{hidden}/*')",
    ]


def test_hidden_unreadable_scoped(engine: QueryEngine, generated: Path):
    for sql in _hidden_reads(generated):
        with pytest.raises(duckdb.PermissionException):
            engine.run_sql(sql)


def test_hidden_unreadable_unscoped(generated: Path):
    con = connect("seen", generated_dir=generated)
    for sql in _hidden_reads(generated):
        with pytest.raises(duckdb.PermissionException):
            con.execute(sql).fetchall()
    con.close()


def test_configuration_is_locked(generated: Path):
    con = connect("seen", generated_dir=generated)
    with pytest.raises(duckdb.Error):
        con.execute("SET enable_external_access = true")
    with pytest.raises(duckdb.Error):
        con.execute("SET allowed_directories = ['/']")
    con.close()


# --- read-only -----------------------------------------------------------------------


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO src.customer (tenant_id) VALUES (1)",
        "UPDATE src.customer SET name = 'x'",
        "DELETE FROM src.customer",
        "CREATE TABLE t (a INTEGER)",
        "DROP VIEW customer",
        "COPY customer TO 'out.parquet'",
        "ATTACH 'other.duckdb'",
        "SET threads = 1",
        "PRAGMA version",
        "CALL pragma_version()",
        "EXPORT DATABASE 'dump'",
        "INSTALL httpfs",
        "LOAD httpfs",
        "SELECT 1; SELECT 2",
        "SELECT 1; DROP VIEW customer",
    ],
)
def test_non_select_rejected(engine: QueryEngine, generated: Path, sql: str):
    before = _files(generated)
    with pytest.raises(ReadOnlyError):
        engine.run_sql(sql)
    assert _files(generated) == before
    assert engine.run_sql("SELECT count(*) FROM customer").rows == [(2,)]
