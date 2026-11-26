"""Parse `datasets/design/schema.sql`, the source of truth for the shared schema."""

import re
from dataclasses import dataclass
from pathlib import Path

SCHEMA_SQL_PATH = Path(__file__).resolve().parents[2] / "design" / "schema.sql"

_TABLE_RE = re.compile(r"CREATE TABLE (\w+) \((.*?)\n\);", re.S)
_TYPE_RE = re.compile(r"^(INTEGER|TEXT|DATE|BOOLEAN|NUMERIC\(\d+, \d+\))\s*(.*)$")


@dataclass(frozen=True)
class SqlColumn:
    name: str
    data_type: str
    modifiers: str
    comment: str


@dataclass(frozen=True)
class SqlTable:
    name: str
    columns: tuple[SqlColumn, ...]
    primary_key: tuple[str, ...]


def parse_schema_sql(path: Path = SCHEMA_SQL_PATH) -> dict[str, SqlTable]:
    text = path.read_text()
    tables: dict[str, SqlTable] = {}
    for match in _TABLE_RE.finditer(text):
        name, body = match.group(1), match.group(2)
        columns: list[SqlColumn] = []
        primary_key: tuple[str, ...] = ()
        for raw in body.split("\n"):
            line = raw.strip()
            if not line:
                continue
            code, _, comment = line.partition("--")
            code = code.strip().rstrip(",").strip()
            if code.startswith("PRIMARY KEY"):
                inner = code[code.index("(") + 1 : code.rindex(")")]
                primary_key = tuple(c.strip() for c in inner.split(","))
                continue
            col_name, _, rest = code.partition(" ")
            type_match = _TYPE_RE.match(rest.strip())
            if type_match is None:
                raise ValueError(f"unparsed column in {name}: {line!r}")
            data_type, modifiers = type_match.group(1), type_match.group(2).strip()
            if "PRIMARY KEY" in modifiers:
                primary_key = (col_name,)
            columns.append(SqlColumn(col_name, data_type, modifiers, comment.strip()))
        tables[name] = SqlTable(name, tuple(columns), primary_key)
    return tables
