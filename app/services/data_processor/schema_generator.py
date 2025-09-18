from typing import Dict, List, Any
from sqlalchemy import Table, Column, Integer, String, Float, Boolean, MetaData, Text, Numeric
from sqlalchemy.dialects.postgresql import JSONB
from app.services.data_processor.schema_def import expected_headers


def _infer_sqlalchemy_type(value: Any):
    if value is None:
        return String
    if isinstance(value, bool):
        return Boolean
    if isinstance(value, int):
        return Integer
    if isinstance(value, float):
        return Float
    if isinstance(value, (dict, list)):
        return JSONB
    # Long text gets Text
    if isinstance(value, str) and len(value) > 255:
        return Text
    return String


def build_table(metadata: MetaData, table_name: str, sample_rows: List[Dict[str, Any]]) -> Table:
    # Strict canonical schema
    columns: List[Column] = [Column("id", Integer, primary_key=True, autoincrement=True)]
    # Canonical columns with fixed types
    columns.append(Column("Potential Buyer 1", String))
    columns.append(Column("Item_Description", Text))
    columns.append(Column("Quantity", Integer))
    columns.append(Column("UQC", String))
    columns.append(Column("Unit_Price", Numeric(18, 2)))
    columns.append(Column("Potential Buyer 2", String))
    columns.append(Column("Potential Buyer 1 Contact Details", String))
    columns.append(Column("Potential Buyer 1 email id", String))
    # Derived fast-search column
    columns.append(Column("part_number", String, index=True))
    return Table(table_name, metadata, *columns)


