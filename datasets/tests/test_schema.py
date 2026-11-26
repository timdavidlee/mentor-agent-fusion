"""The Python table definitions must not drift from `datasets/design/schema.sql`."""

from generator.schema import TABLES, create_pg_sql_table_schema
from generator.schema.sql_parser import parse_schema_sql


def test_same_tables_in_same_order() -> None:
    assert list(parse_schema_sql()) == list(TABLES)
    assert len(TABLES) == 17


def test_every_column_matches_schema_sql() -> None:
    parsed = parse_schema_sql()
    for name, defn in TABLES.items():
        sql = parsed[name]
        assert [c.name for c in defn.pg_columns] == [c.name for c in sql.columns], name
        assert [c.data_type for c in defn.pg_columns] == [c.data_type for c in sql.columns], name
        assert [c.modifiers for c in defn.pg_columns] == [c.modifiers for c in sql.columns], name
        assert [c.llm_description for c in defn.pg_columns] == [c.comment for c in sql.columns]
        assert defn.primary_key == list(sql.primary_key), name


def test_every_table_has_tenant_id() -> None:
    for name in TABLES:
        assert "tenant_id" in create_pg_sql_table_schema(name).column_names
