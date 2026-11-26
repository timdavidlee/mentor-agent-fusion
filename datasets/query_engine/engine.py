"""DuckDB over the generator's visible Parquet files, shaped like a customer database.

Two entry points:

- `connect()` returns a raw DuckDB connection for development. Tenant scoping is optional.
- `QueryEngine` is what an agent tool wraps. It is always scoped to one tenant and only
  runs read-only statements.

In both, each `schema.sql` table is a view in the `main` schema, carrying the schema's
nominal column comments, and nothing under `hidden/` can be read.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import duckdb

from query_engine.schema import SCHEMA_SQL_PATH, Table, load_schema

GENERATED_DIR = Path(__file__).resolve().parents[1] / "generated"

Split = Literal["seen", "held_out"]
SPLITS: tuple[Split, ...] = ("seen", "held_out")

# Schema holding the in-memory tenant slice in scoped mode; views in `main` read from it.
_SOURCE_SCHEMA = "src"

_READ_ONLY_STATEMENTS = {duckdb.StatementType.SELECT, duckdb.StatementType.EXPLAIN}


class ReadOnlyError(ValueError):
    """Raised when an agent submits anything other than a single read-only statement."""


@dataclass(frozen=True)
class QueryResult:
    columns: list[str]
    rows: list[tuple[Any, ...]]
    truncated: bool  # True when more rows existed than max_rows


@dataclass(frozen=True)
class ColumnInfo:
    name: str
    type: str
    comment: str | None


def _quote_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def visible_dir(split: Split, generated_dir: Path = GENERATED_DIR) -> Path:
    if split not in SPLITS:
        raise ValueError(f"split must be one of {SPLITS}, got {split!r}")
    return (generated_dir / split / "visible").resolve()


def _select_list(table: Table, source: str | None) -> str:
    """Columns in schema order, cast to the schema type. With no source, a typed empty row."""
    parts = []
    for col in table.columns:
        expr = _quote_ident(col.name) if source else "NULL"
        parts.append(f"CAST({expr} AS {col.duckdb_type}) AS {_quote_ident(col.name)}")
    return ",\n  ".join(parts)


def connect(
    split: Split = "seen",
    tenant_id: int | None = None,
    *,
    generated_dir: Path = GENERATED_DIR,
    schema_path: Path = SCHEMA_SQL_PATH,
) -> duckdb.DuckDBPyConnection:
    """Open an in-memory DuckDB with one view per `schema.sql` table.

    Without `tenant_id`, views read `<split>/visible/<table>.parquet` directly and the
    connection may read files only inside that `visible/` directory.

    With `tenant_id`, that tenant's rows are first copied into memory and file access is
    then switched off entirely, so not even `read_parquet` on a visible file can reach
    another tenant.

    A table with no Parquet file becomes an empty view with the schema's columns, so every
    split shows the same tables. Configuration is locked once the views exist. The raw
    connection still accepts DDL and `COPY`; use `QueryEngine` for agents.
    """
    visible = visible_dir(split, generated_dir)
    if not visible.is_dir():
        raise FileNotFoundError(f"no visible data at {visible}; run the generator first")
    tables = load_schema(schema_path)
    tenant = None if tenant_id is None else int(tenant_id)

    con = duckdb.connect(":memory:")
    try:
        if tenant is not None:
            con.execute(f"CREATE SCHEMA {_SOURCE_SCHEMA}")
        for table in tables.values():
            parquet = visible / f"{table.name}.parquet"
            if not parquet.is_file():
                body = f"SELECT\n  {_select_list(table, None)}\nWHERE false"
            elif tenant is None:
                body = (
                    f"SELECT\n  {_select_list(table, 'p')}\n"
                    f"FROM read_parquet({_quote_literal(str(parquet))}) AS p"
                )
            else:
                source = f"{_SOURCE_SCHEMA}.{_quote_ident(table.name)}"
                con.execute(
                    f"CREATE TABLE {source} AS SELECT\n  {_select_list(table, 'p')}\n"
                    f"FROM read_parquet({_quote_literal(str(parquet))}) AS p "
                    f"WHERE p.tenant_id = {tenant}"
                )
                body = f"SELECT * FROM {source}"
            view = _quote_ident(table.name)
            con.execute(f"CREATE VIEW {view} AS {body}")
            for col in table.columns:
                if col.comment:
                    con.execute(
                        f"COMMENT ON COLUMN {view}.{_quote_ident(col.name)} "
                        f"IS {_quote_literal(col.comment)}"
                    )

        if tenant is None:
            con.execute(f"SET allowed_directories = [{_quote_literal(str(visible) + '/')}]")
        con.execute("SET enable_external_access = false")
        con.execute("SET autoinstall_known_extensions = false")
        con.execute("SET autoload_known_extensions = false")
        con.execute("SET lock_configuration = true")
    except BaseException:
        con.close()
        raise
    return con


class QueryEngine:
    """Agent-facing access to one tenant's visible data. Read-only.

    >>> engine = QueryEngine("seen", tenant_id=7)
    >>> engine.list_tables()
    >>> engine.run_sql("SELECT count(*) FROM customer").rows
    """

    def __init__(
        self,
        split: Split,
        tenant_id: int,
        *,
        generated_dir: Path = GENERATED_DIR,
        schema_path: Path = SCHEMA_SQL_PATH,
    ) -> None:
        self.split = split
        self.tenant_id = int(tenant_id)
        self._con = connect(
            split, self.tenant_id, generated_dir=generated_dir, schema_path=schema_path
        )

    def close(self) -> None:
        self._con.close()

    def __enter__(self) -> "QueryEngine":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def run_sql(self, sql: str, max_rows: int | None = 1000) -> QueryResult:
        """Run one SELECT (or EXPLAIN) and return at most `max_rows` rows."""
        statements = duckdb.extract_statements(sql)
        if len(statements) != 1:
            raise ReadOnlyError(f"expected exactly one SQL statement, got {len(statements)}")
        statement = statements[0]
        if statement.type not in _READ_ONLY_STATEMENTS:
            raise ReadOnlyError(f"only SELECT queries are allowed, got {statement.type.name}")
        cursor = self._con.execute(statement)
        columns = [d[0] for d in cursor.description or []]
        if max_rows is None:
            return QueryResult(columns, cursor.fetchall(), truncated=False)
        rows = cursor.fetchmany(max_rows + 1)
        return QueryResult(columns, rows[:max_rows], truncated=len(rows) > max_rows)

    def list_tables(self) -> list[str]:
        rows = self._con.execute(
            "SELECT view_name FROM duckdb_views() "
            "WHERE schema_name = 'main' AND NOT internal ORDER BY view_name"
        ).fetchall()
        return [r[0] for r in rows]

    def describe(self, table: str) -> list[ColumnInfo]:
        """Columns of `table` in order, with type and the schema's nominal comment."""
        rows = self._con.execute(
            "SELECT column_name, data_type, comment FROM duckdb_columns() "
            "WHERE schema_name = 'main' AND table_name = ? ORDER BY column_index",
            [table],
        ).fetchall()
        if not rows:
            raise KeyError(f"no such table: {table!r}")
        return [ColumnInfo(name, type_, comment) for name, type_, comment in rows]
