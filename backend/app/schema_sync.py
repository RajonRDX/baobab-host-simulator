"""
schema_sync.py — Non-Destructive Database Schema Synchronizer
Automatically creates missing tables and adds missing nullable columns to existing
SQLite / PostgreSQL tables without deleting or altering existing data.
"""

import logging
from typing import Dict, List, Set
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase

logger = logging.getLogger("rajon.schema_sync")


def _compile_column_type(column, dialect) -> str:
    try:
        return column.type.compile(dialect=dialect)
    except Exception:
        return "TEXT"


def synchronize_database_schema(engine: Engine, base_cls: type[DeclarativeBase]) -> Dict[str, List[str]]:
    """
    1. Creates any brand-new tables registered on `base_cls.metadata`.
    2. Inspects every existing table and issues `ALTER TABLE ... ADD COLUMN ...`
       for any newly defined ORM columns that do not yet exist in the physical database.
    Never drops tables, never drops columns, and never deletes existing rows.
    """
    summary: Dict[str, List[str]] = {"created_tables": [], "added_columns": []}

    inspector = inspect(engine)
    existing_tables: Set[str] = set(inspector.get_table_names())

    # 1. Create missing tables first
    base_cls.metadata.create_all(bind=engine)

    inspector_after = inspect(engine)
    after_tables: Set[str] = set(inspector_after.get_table_names())
    for tbl in sorted(after_tables - existing_tables):
        summary["created_tables"].append(tbl)
        logger.info("[SchemaSync] Created new table: %s", tbl)

    # 2. Check existing tables for missing columns
    with engine.begin() as conn:
        for table_name, table_obj in base_cls.metadata.tables.items():
            if table_name not in existing_tables:
                continue

            db_cols = {c["name"].lower() for c in inspector_after.get_columns(table_name)}
            for col in table_obj.columns:
                if col.name.lower() in db_cols:
                    continue

                col_type_sql = _compile_column_type(col, engine.dialect)
                default_clause = ""

                # If a column has a simple scalar default and is non-nullable, provide a safe default
                if not col.nullable and col.default is not None and getattr(col.default, "is_scalar", False):
                    arg = col.default.arg
                    if isinstance(arg, bool):
                        default_clause = f" DEFAULT {1 if arg else 0}" if engine.dialect.name == "sqlite" else f" DEFAULT {'TRUE' if arg else 'FALSE'}"
                    elif isinstance(arg, (int, float)):
                        default_clause = f" DEFAULT {arg}"
                    elif isinstance(arg, str):
                        safe_str = arg.replace("'", "''")
                        default_clause = f" DEFAULT '{safe_str}'"

                alter_sql = f'ALTER TABLE "{table_name}" ADD COLUMN "{col.name}" {col_type_sql}{default_clause}'
                conn.execute(text(alter_sql))
                summary["added_columns"].append(f"{table_name}.{col.name}")
                logger.info("[SchemaSync] Added missing column: %s.%s (%s)", table_name, col.name, col_type_sql)

    return summary
