"""Regenerate `tables.py` from `schema.sql`: `uv run python -m generator.schema.emit`.

`tests/test_schema.py` fails whenever the two differ, so rerun this after editing the
schema (and `ruff format` the result).
"""

from pathlib import Path

from generator.schema.sql_parser import parse_schema_sql

TARGET = Path(__file__).with_name("tables.py")


def emit() -> str:
    out = [
        '"""Python definitions of the 17 shared tables.\n\n'
        "Mirrors `datasets/design/schema.sql`; "
        '`tests/test_schema.py` fails if the two drift.\n"""\n\n',
        "from generator.schema.pg import CreatePgTableSql, PgColumn\n\n",
        "TABLES: dict[str, CreatePgTableSql] = {\n",
    ]
    for t in parse_schema_sql().values():
        out.append(
            f"    {t.name!r}: CreatePgTableSql(\n        pg_table={t.name!r},\n"
            f"        primary_key={list(t.primary_key)!r},\n        pg_columns=[\n"
        )
        for c in t.columns:
            out.append(
                f"            PgColumn(name={c.name!r}, data_type={c.data_type!r}, "
                f"modifiers={c.modifiers!r}, llm_description={c.comment!r}),\n"
            )
        out.append("        ],\n    ),\n")
    out.append("}\n")
    return "".join(out)


if __name__ == "__main__":
    TARGET.write_text(emit())
