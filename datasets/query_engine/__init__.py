"""Local SQL over the generated visible Parquet files, via in-process DuckDB."""

from query_engine.engine import (
    GENERATED_DIR,
    SPLITS,
    ColumnInfo,
    QueryEngine,
    QueryResult,
    ReadOnlyError,
    Split,
    connect,
    visible_dir,
)
from query_engine.schema import Column, Table, load_schema

__all__ = [
    "GENERATED_DIR",
    "SPLITS",
    "Column",
    "ColumnInfo",
    "QueryEngine",
    "QueryResult",
    "ReadOnlyError",
    "Split",
    "Table",
    "connect",
    "load_schema",
    "visible_dir",
]
