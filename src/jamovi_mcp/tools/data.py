"""Data operation tools for jamovi MCP."""

from __future__ import annotations

from typing import Any

from ..connection import JamoviConnection
from ..proto import jamovi_pb2 as jcoms


def _measure_type_name(mt: int) -> str:
    names = {0: "none", 2: "nominal", 3: "ordinal", 4: "continuous"}
    return names.get(mt, "none")


def _data_type_name(dt: int) -> str:
    names = {0: "none", 1: "integer", 2: "decimal", 3: "text"}
    return names.get(dt, "none")


def _cell_to_python(cell: Any) -> Any:
    if cell.missing:
        return None
    if cell.HasField("i"):
        return cell.i
    if cell.HasField("d"):
        return cell.d
    if cell.HasField("s"):
        return cell.s
    if cell.HasField("o"):
        return None
    return None


async def jamovi_get_schema(conn: JamoviConnection) -> dict[str, Any]:
    """Get the dataset schema: columns, types, levels, row count."""
    request = jcoms.InfoRequest()
    payload = await conn.send(request, payload_type="InfoRequest")

    response = jcoms.InfoResponse()
    response.ParseFromString(payload)

    schema = response.schema
    columns = []
    for col in schema.columns:
        columns.append({
            "id": col.id,
            "name": col.name,
            "index": col.index,
            "columnType": col.columnType,
            "dataType": _data_type_name(col.dataType),
            "measureType": _measure_type_name(col.measureType),
            "width": col.width,
            "hasLevels": col.hasLevels,
            "levels": [
                {"label": lvl.label, "value": lvl.value}
                for lvl in col.levels
            ] if col.hasLevels else [],
            "formula": col.formula if col.formula else None,
            "description": col.description if col.description else None,
            "hidden": col.hidden,
            "active": col.active,
        })

    return {
        "hasDataSet": response.hasDataSet,
        "title": response.title,
        "path": response.path,
        "rowCount": schema.rowCount,
        "columnCount": schema.columnCount,
        "totalColumns": len(schema.columns),
        "totalRowCount": schema.vRowCount,
        "columns": columns,
    }


async def jamovi_get_data(
    conn: JamoviConnection,
    row_start: int = 0,
    row_count: int = 50,
    column_start: int = 0,
    column_count: int | None = None,
) -> dict[str, Any]:
    """Get data rows from the dataset."""
    request = jcoms.DataSetRR()
    request.op = jcoms.GetSet.GET
    request.incData = True

    block = request.data.add()
    block.rowStart = row_start
    block.rowCount = row_count
    block.columnStart = column_start
    block.columnCount = column_count if column_count is not None else 1000

    payload = await conn.send(request, payload_type="DataSetRR")
    response = jcoms.DataSetRR()
    response.ParseFromString(payload)

    rows: list[list[Any]] = []
    for block in response.data:
        total_vals = len(block.values)
        n_rows = block.rowCount
        if n_rows <= 0 or total_vals == 0:
            continue

        n_cols = block.columnCount
        if n_cols <= 0:
            n_cols = total_vals // n_rows
        n_cols = min(n_cols, total_vals // n_rows)

        for row_offset in range(n_rows):
            row: list[Any] = []
            for column_offset in range(n_cols):
                value_index = column_offset * n_rows + row_offset
                row.append(_cell_to_python(block.values[value_index]))
            rows.append(row)

    return {
        "rowStart": row_start,
        "rowCount": len(rows),
        "rows": rows,
    }


async def jamovi_set_data(
    conn: JamoviConnection,
    row: int,
    column: int,
    value: int | float | str | None,
) -> dict[str, Any]:
    """Set a single cell value."""
    request = jcoms.DataSetRR()
    request.op = jcoms.GetSet.SET
    request.incData = True

    block = request.data.add()
    block.rowStart = row
    block.rowCount = 1
    block.columnStart = column
    block.columnCount = 1

    cell = block.values.add()
    if value is None:
        cell.o = jcoms.SpecialValues.MISSING
    elif isinstance(value, int):
        cell.i = value
    elif isinstance(value, float):
        cell.d = value
    else:
        cell.s = str(value)

    payload = await conn.send(request, payload_type="DataSetRR")
    response = jcoms.DataSetRR()
    response.ParseFromString(payload)

    return {"status": "complete", "row": row, "column": column, "value": value}
