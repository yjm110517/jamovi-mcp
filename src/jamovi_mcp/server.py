"""MCP server for jamovi statistical analysis."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from .config import JAMOVI_PORT
from .connection import JamoviConnection, ConnectionError
from .engine import EngineManager, EngineError
from .analyses import list_analyses, get_analysis_options

from .tools.files import jamovi_open as _jamovi_open
from .tools.files import jamovi_save as _jamovi_save
from .tools.data import jamovi_get_schema as _jamovi_get_schema
from .tools.data import jamovi_get_data as _jamovi_get_data
from .tools.data import jamovi_set_data as _jamovi_set_data
from .tools.analysis import jamovi_run_analysis as _jamovi_run_analysis
from .tools.analysis import jamovi_get_analysis as _jamovi_get_analysis
from .tools.analysis import jamovi_list_analyses_impl
from .tools.analysis import jamovi_get_analysis_options_impl
from .tools.analysis import jamovi_export_results as _jamovi_export_results

log = logging.getLogger(__name__)

TOOLS = [
    Tool(
        name="jamovi_open",
        description="Open a data file in jamovi. Supports .omv, .csv, .sav, .xlsx, .ods, .dta, .sas7bdat, .por, .txt formats.",
        inputSchema={
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Absolute path to the data file to open.",
                },
            },
            "required": ["file_path"],
        },
    ),
    Tool(
        name="jamovi_get_schema",
        description="Get the dataset schema: column names, types, measure types, levels, and row count.",
        inputSchema={
            "type": "object",
            "properties": {},
        },
    ),
    Tool(
        name="jamovi_get_data",
        description="Get rows of data from the dataset.",
        inputSchema={
            "type": "object",
            "properties": {
                "row_start": {
                    "type": "integer",
                    "description": "First row index (0-based).",
                    "default": 0,
                },
                "row_count": {
                    "type": "integer",
                    "description": "Number of rows to retrieve.",
                    "default": 50,
                },
                "column_start": {
                    "type": "integer",
                    "description": "First column index (0-based).",
                    "default": 0,
                },
                "column_count": {
                    "type": "integer",
                    "description": "Number of columns. Omit for all.",
                },
            },
        },
    ),
    Tool(
        name="jamovi_set_data",
        description="Set a single cell value in the dataset.",
        inputSchema={
            "type": "object",
            "properties": {
                "row": {
                    "type": "integer",
                    "description": "Row index (0-based).",
                },
                "column": {
                    "type": "integer",
                    "description": "Column index (0-based).",
                },
                "value": {
                    "description": "Cell value (integer, number, string, or null for missing).",
                },
            },
            "required": ["row", "column", "value"],
        },
    ),
    Tool(
        name="jamovi_list_analyses",
        description="List all available statistical analyses in jamovi.",
        inputSchema={
            "type": "object",
            "properties": {},
        },
    ),
    Tool(
        name="jamovi_get_analysis_options",
        description="Get the options/parameters schema for a specific analysis.",
        inputSchema={
            "type": "object",
            "properties": {
                "ns": {
                    "type": "string",
                    "description": "Module namespace, e.g. 'jmv'.",
                },
                "name": {
                    "type": "string",
                    "description": "Analysis name, e.g. 'ttestIS'.",
                },
            },
            "required": ["ns", "name"],
        },
    ),
    Tool(
        name="jamovi_run_analysis",
        description="Run a statistical analysis on the current dataset.",
        inputSchema={
            "type": "object",
            "properties": {
                "ns": {
                    "type": "string",
                    "description": "Module namespace (e.g. 'jmv').",
                },
                "name": {
                    "type": "string",
                    "description": "Analysis name (e.g. 'ttestIS', 'anova', 'linReg').",
                },
                "options": {
                    "type": "object",
                    "description": "Analysis options. Use jamovi_get_analysis_options to see available options.",
                },
                "analysis_id": {
                    "type": "integer",
                    "description": "Unique even ID for this analysis (2, 4, 6...).",
                    "default": 2,
                },
            },
            "required": ["ns", "name", "options"],
        },
    ),
    Tool(
        name="jamovi_get_analysis",
        description="Get the results of a previously run analysis.",
        inputSchema={
            "type": "object",
            "properties": {
                "analysis_id": {
                    "type": "integer",
                    "description": "The analysis ID to retrieve.",
                },
            },
            "required": ["analysis_id"],
        },
    ),
    Tool(
        name="jamovi_export_results",
        description="Export analysis results in a specific format.",
        inputSchema={
            "type": "object",
            "properties": {
                "analysis_id": {
                    "type": "integer",
                    "description": "The analysis ID to export.",
                },
                "fmt": {
                    "type": "string",
                    "description": "Export format: 'txt' or 'html'.",
                    "default": "txt",
                },
            },
            "required": ["analysis_id"],
        },
    ),
    Tool(
        name="jamovi_save",
        description="Save the current dataset to a file (.omv format).",
        inputSchema={
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to save the file.",
                },
                "overwrite": {
                    "type": "boolean",
                    "description": "Whether to overwrite if file exists.",
                    "default": True,
                },
            },
            "required": ["file_path"],
        },
    ),
]

TOOL_MAP = {
    "jamovi_open": _jamovi_open,
    "jamovi_get_schema": _jamovi_get_schema,
    "jamovi_get_data": _jamovi_get_data,
    "jamovi_set_data": _jamovi_set_data,
    "jamovi_list_analyses": jamovi_list_analyses_impl,
    "jamovi_get_analysis_options": jamovi_get_analysis_options_impl,
    "jamovi_run_analysis": _jamovi_run_analysis,
    "jamovi_get_analysis": _jamovi_get_analysis,
    "jamovi_export_results": _jamovi_export_results,
    "jamovi_save": _jamovi_save,
}

CONN_REQUIRED = {
    "jamovi_open",
    "jamovi_get_schema",
    "jamovi_get_data",
    "jamovi_set_data",
    "jamovi_run_analysis",
    "jamovi_get_analysis",
    "jamovi_export_results",
    "jamovi_save",
}


async def run_server() -> None:
    engine = EngineManager(port=JAMOVI_PORT)
    conn: JamoviConnection | None = None

    server = Server("jamovi-mcp")

    @server.list_tools()
    async def handle_list_tools() -> list[Tool]:
        return TOOLS

    @server.call_tool()
    async def handle_call_tool(
        name: str,
        arguments: dict[str, Any],
    ) -> list[TextContent]:
        nonlocal conn

        if name in CONN_REQUIRED and conn is None:
            return [TextContent(
                type="text",
                text="Error: jamovi engine is not connected. "
                     "Please ensure the engine is running."
            )]

        try:
            func = TOOL_MAP[name]
            if name in ("jamovi_list_analyses", "jamovi_get_analysis_options"):
                if name == "jamovi_get_analysis_options":
                    result = await func(
                        ns=arguments["ns"],
                        name=arguments["name"],
                    )
                else:
                    result = await func()
            elif name in CONN_REQUIRED:
                kwargs = dict(arguments)
                kwargs["conn"] = conn
                result = await func(**kwargs)
            else:
                result = await func(**arguments)

            import json
            return [TextContent(
                type="text",
                text=json.dumps(result, ensure_ascii=False, indent=2, default=str),
            )]
        except ConnectionError as e:
            return [TextContent(
                type="text",
                text=f"Connection error: {e}",
            )]
        except Exception as e:
            log.exception("Error calling tool %s", name)
            return [TextContent(
                type="text",
                text=f"Error: {e}",
            )]

    try:
        log.info("Starting jamovi engine...")
        await engine.start()
        log.info(
            "Engine started on ports %d/%d/%d, access_key=%s",
            engine.main_port, engine.analysis_port,
            engine.results_port, engine.access_key,
        )

        conn = JamoviConnection(
            base_url=engine.base_url,
            ws_url=engine.ws_url,
            access_key=engine.access_key,
        )
        await conn.connect()
        log.info("Connected to jamovi instance %s", conn.instance_id)

        async with stdio_server() as (reader, writer):
            await server.run(reader, writer, server.create_initialization_options())

    finally:
        if conn:
            await conn.disconnect()
        await engine.stop()
