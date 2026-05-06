from __future__ import annotations

import pytest

from jamovi_mcp.proto import jamovi_pb2 as jcoms
from jamovi_mcp.tools.data import jamovi_get_data, jamovi_set_data


class FakeConnection:
    def __init__(self, payload: bytes | None = None) -> None:
        self.payload = payload or jcoms.DataSetRR().SerializeToString()
        self.sent_message = None
        self.sent_payload_type = None

    async def send(self, message, *, payload_type: str = "") -> bytes:
        self.sent_message = message
        self.sent_payload_type = payload_type
        return self.payload


@pytest.mark.asyncio
async def test_get_data_converts_column_major_blocks_to_rows() -> None:
    response = jcoms.DataSetRR()
    block = response.data.add()
    block.rowStart = 0
    block.rowCount = 4
    block.columnStart = 0
    block.columnCount = 2

    for value in ("A", "A", "B", "B"):
        block.values.add().s = value
    for value in (1, 2, 5, 6):
        block.values.add().i = value

    conn = FakeConnection(response.SerializeToString())

    result = await jamovi_get_data(
        conn,
        row_start=0,
        row_count=4,
        column_start=0,
        column_count=2,
    )

    assert result["rowStart"] == 0
    assert result["rowCount"] == 4
    assert result["rows"] == [["A", 1], ["A", 2], ["B", 5], ["B", 6]]


@pytest.mark.asyncio
async def test_set_data_sends_inc_data_and_cell_selection() -> None:
    conn = FakeConnection()

    result = await jamovi_set_data(conn, row=3, column=2, value=10)

    request = conn.sent_message
    assert conn.sent_payload_type == "DataSetRR"
    assert request.op == jcoms.GetSet.SET
    assert request.incData is True

    block = request.data[0]
    assert block.rowStart == 3
    assert block.rowCount == 1
    assert block.columnStart == 2
    assert block.columnCount == 1
    assert block.values[0].i == 10
    assert result == {"status": "complete", "row": 3, "column": 2, "value": 10}


@pytest.mark.asyncio
async def test_set_data_uses_special_missing_for_none() -> None:
    conn = FakeConnection()

    await jamovi_set_data(conn, row=0, column=0, value=None)

    cell = conn.sent_message.data[0].values[0]
    assert cell.o == jcoms.SpecialValues.MISSING
