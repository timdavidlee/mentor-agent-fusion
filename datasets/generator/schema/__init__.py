"""The shared schema: Python table definitions checked against `schema.sql`."""

from generator.schema.pg import CreatePgTableSql, PgColumn, arrow_type
from generator.schema.tables import TABLES

TABLE_ORDER: list[str] = list(TABLES)


def create_pg_sql_table_schema(table: str) -> CreatePgTableSql:
    return TABLES[table]


__all__ = [
    "TABLES",
    "TABLE_ORDER",
    "CreatePgTableSql",
    "PgColumn",
    "arrow_type",
    "create_pg_sql_table_schema",
]
