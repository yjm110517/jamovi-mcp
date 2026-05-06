"""File operation tools for jamovi MCP."""

from __future__ import annotations

from ..connection import JamoviConnection


async def jamovi_open(
    conn: JamoviConnection,
    file_path: str,
) -> dict:
    """Open a data file in jamovi. Reconnects to the new data instance."""
    new_id = await conn.connect_with_file(file_path)
    return {
        "status": "ok",
        "file": file_path,
        "instanceId": new_id,
    }


async def jamovi_save(
    conn: JamoviConnection,
    file_path: str,
    overwrite: bool = True,
) -> dict:
    """Save the current dataset to a file."""
    result = await conn.save_file(file_path, overwrite=overwrite)
    result.setdefault("path", file_path)
    result["status"] = "ok"
    return result
