"""Read table and column definitions from `datasets/design/schema.sql`.

Kept separate from the generator's parser on purpose: the query engine only needs names,
types and the nominal column comments, and should not depend on generator code.
"""

import re
from dataclasses import dataclass
from pathlib import Path

SCHEMA_SQL_PATH = Path(__file__).resolve().parents[1] / "design" / "schema.sql"

_TABLE_RE = re.compile(r"CREATE TABLE (\w+) \((.*?)\n\);", re.S)
_COLUMN_RE = re.compile(r"^(\w+)\s+(INTEGER|TEXT|DATE|BOOLEAN|NUMERIC\(\d+,\s*\d+\))")

# schema.sql is written in Postgres types; these are the DuckDB equivalents.
_DUCKDB_TYPES = {"INTEGER": "INTEGER", "TEXT": "VARCHAR", "DATE": "DATE", "BOOLEAN": "BOOLEAN"}


@dataclass(frozen=True)
class Column:
    name: str
    sql_type: str  # as written in schema.sql, e.g. NUMERIC(12, 2)
    comment: str  # nominal meaning; empty when schema.sql has none

    @property
    def duckdb_type(self) -> str:
        if self.sql_type.startswith("NUMERIC"):
            return self.sql_type.replace("NUMERIC", "DECIMAL")
        return _DUCKDB_TYPES[self.sql_type]


@dataclass(frozen=True)
class Table:
    name: str
    columns: tuple[Column, ...]


def load_schema(path: Path = SCHEMA_SQL_PATH) -> dict[str, Table]:
    """Return every table in `schema.sql`, in file order."""
    tables: dict[str, Table] = {}
    for match in _TABLE_RE.finditer(path.read_text()):
        name, body = match.group(1), match.group(2)
        columns: list[Column] = []
        for raw in body.splitlines():
            code, _, comment = raw.partition("--")
            code = code.strip()
            if not code or code.startswith(("PRIMARY KEY", "UNIQUE", "FOREIGN KEY", "CHECK")):
                continue
            col = _COLUMN_RE.match(code)
            if col is None:
                raise ValueError(f"unparsed column in {name}: {raw.strip()!r}")
            columns.append(Column(col.group(1), col.group(2), comment.strip()))
        tables[name] = Table(name, tuple(columns))
    if not tables:
        raise ValueError(f"no CREATE TABLE statements found in {path}")
    return tables
