"""Table-definition models, in the style of the adorable-thunder `CreatePgTableSql`."""

import re

import pyarrow as pa
from pydantic import BaseModel

_NUMERIC_RE = re.compile(r"NUMERIC\((\d+), (\d+)\)")


def arrow_type(data_type: str) -> pa.DataType:
    if data_type == "INTEGER":
        return pa.int64()
    if data_type == "TEXT":
        return pa.string()
    if data_type == "DATE":
        return pa.date32()
    if data_type == "BOOLEAN":
        return pa.bool_()
    match = _NUMERIC_RE.fullmatch(data_type)
    if match:
        return pa.decimal128(int(match.group(1)), int(match.group(2)))
    raise ValueError(f"unknown SQL type {data_type!r}")


class PgColumn(BaseModel):
    name: str
    data_type: str
    modifiers: str = ""
    llm_description: str = "N/A"

    @property
    def sql_row(self) -> str:
        return f"{self.name} {self.data_type} {self.modifiers}".strip()

    @property
    def nullable(self) -> bool:
        return "NOT NULL" not in self.modifiers and "PRIMARY KEY" not in self.modifiers


class CreatePgTableSql(BaseModel):
    pg_schema: str = "public"
    pg_table: str
    pg_columns: list[PgColumn]
    primary_key: list[str]
    llm_description: str = "N/A"

    @property
    def column_names(self) -> list[str]:
        return [c.name for c in self.pg_columns]

    @property
    def sql_statement(self) -> str:
        columns = ",\n    ".join(c.sql_row for c in self.pg_columns)
        return f"CREATE TABLE IF NOT EXISTS {self.pg_schema}.{self.pg_table} (\n    {columns}\n);"

    def arrow_schema(self) -> pa.Schema:
        return pa.schema(
            [
                pa.field(c.name, arrow_type(c.data_type), nullable=c.nullable)
                for c in self.pg_columns
            ]
        )
