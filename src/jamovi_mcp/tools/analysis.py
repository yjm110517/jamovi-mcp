"""Analysis operation tools for jamovi MCP."""

from __future__ import annotations

from typing import Any

from ..analyses import get_analysis_options, list_analyses
from ..connection import JamoviConnection
from ..proto import jamovi_pb2 as jcoms


def _build_options(
    options: list[dict[str, Any]],
    option_values: dict[str, Any],
    ns: str,
) -> jcoms.AnalysisOptions:
    """Build an AnalysisOptions protobuf message from user values and schema."""
    ao = jcoms.AnalysisOptions()
    ao.hasNames = True

    for opt_def in options:
        name = opt_def["name"]
        if name not in option_values:
            continue
        value = option_values[name]
        opt_type = opt_def.get("type", "String")

        ao.names.append(name)
        entry = ao.options.add()

        if opt_type == "Variables":
            # variables are passed as a list of column names/ids wrapped in a sub-AnalysisOptions
            inner = jcoms.AnalysisOptions()
            inner.hasNames = False
            for var in (value if isinstance(value, list) else [value]):
                inner.options.add().s = str(var)
            entry.c.CopyFrom(inner)
        elif opt_type == "Variable":
            entry.s = str(value)
        elif opt_type == "Number":
            entry.d = float(value)
        elif opt_type == "Bool":
            entry.i = 1 if value else 0
        elif opt_type == "List":
            entry.s = str(value)
        elif opt_type == "Integer":
            entry.i = int(value)
        else:
            entry.s = str(value)

    return ao


def _results_to_dict(element: Any) -> dict[str, Any] | None:
    """Convert a ResultsElement to a JSON-safe dict."""
    if element is None:
        return None

    result: dict[str, Any] = {
        "name": element.name,
        "title": element.title,
        "status": element.status,
    }

    if element.HasField("table"):
        table = element.table
        columns = []
        for col in table.columns:
            cells = []
            for cell in col.cells:
                if cell.HasField("i"):
                    cells.append(cell.i)
                elif cell.HasField("d"):
                    cells.append(cell.d)
                elif cell.HasField("s"):
                    cells.append(cell.s)
                elif cell.HasField("o"):
                    cells.append(cell.o)
                else:
                    cells.append(None)
            columns.append({
                "name": col.name,
                "title": col.title,
                "type": col.type,
                "cells": cells,
                "sortable": col.sortable,
            })
        result["table"] = {
            "columns": columns,
            "rowNames": list(table.rowNames),
            "notes": [
                {"key": n.key, "note": n.note}
                for n in table.notes
            ],
            "asText": table.asText,
        }
    elif element.HasField("array"):
        arr = element.array
        children = []
        for child in arr.elements:
            c = _results_to_dict(child)
            if c:
                children.append(c)
        result["array"] = {"elements": children}
    elif element.HasField("group"):
        grp = element.group
        children = []
        for child in grp.elements:
            c = _results_to_dict(child)
            if c:
                children.append(c)
        result["group"] = {"elements": children}
    elif element.HasField("preformatted"):
        result["preformatted"] = element.preformatted
    elif element.HasField("syntax"):
        result["syntax"] = element.syntax
    elif element.HasField("html"):
        result["html"] = {"content": element.html.content}
    elif element.HasField("notice"):
        result["notice"] = {
            "content": element.notice.content,
            "type": element.notice.type,
        }
    elif element.HasField("image"):
        result["image"] = {
            "path": element.image.path,
            "width": element.image.width,
            "height": element.image.height,
        }

    if element.HasField("error") and element.error.message:
        result["error"] = {"message": element.error.message}

    return result


async def jamovi_list_analyses_impl() -> list[dict[str, Any]]:
    """List all available analysis types."""
    return list_analyses()


async def jamovi_get_analysis_options_impl(
    ns: str,
    name: str,
) -> dict[str, Any] | None:
    """Get the options schema for a specific analysis."""
    return get_analysis_options(ns, name)


async def jamovi_run_analysis(
    conn: JamoviConnection,
    ns: str,
    name: str,
    options: dict[str, Any],
    analysis_id: int = 2,
) -> dict[str, Any]:
    """Run a statistical analysis.

    Args:
        conn: The jamovi connection.
        ns: The module namespace (e.g. "jmv").
        name: The analysis name (e.g. "ttestIS").
        options: Dict of option name → value.
        analysis_id: Unique even ID for this analysis. Must be even (2, 4, 6...).
    """
    if analysis_id % 2 != 0:
        return {"error": {"message": "analysis_id must be an even number (2, 4, 6...)"}}

    schema = get_analysis_options(ns, name)
    opt_defs = schema["options"] if schema else []

    request = jcoms.AnalysisRequest()
    request.instanceId = conn.instance_id
    request.analysisId = analysis_id
    request.name = name
    request.ns = ns
    request.perform = jcoms.AnalysisRequest.Perform.RUN
    request.options.CopyFrom(_build_options(opt_defs, options, ns))

    # Send the request - server responds immediately with ANALYSIS_NONE
    payload = await conn.send(request, payload_type="AnalysisRequest")
    ack = jcoms.AnalysisResponse()
    ack.ParseFromString(payload)

    # If already complete (e.g. restored from cache), return it
    if ack.status == jcoms.AnalysisStatus.ANALYSIS_COMPLETE:
        return _build_analysis_result(ack)

    # Wait for the asynchronous result message with matching analysisId
    result_payload = await conn.wait_for_analysis_result(analysis_id)
    response = jcoms.AnalysisResponse()
    response.ParseFromString(result_payload)

    return _build_analysis_result(response)


def _build_analysis_result(response: Any) -> dict[str, Any]:
    """Build a JSON-safe dict from an AnalysisResponse."""
    return {
        "analysisId": response.analysisId,
        "name": response.name,
        "ns": response.ns,
        "title": response.title if response.hasTitle else "",
        "status": response.status,
        "hasResults": response.HasField("results"),
        "results": _results_to_dict(response.results) if response.HasField("results") else None,
        "error": (
            {"message": response.error.message}
            if response.HasField("error") and response.error.message
            else None
        ),
    }


async def jamovi_get_analysis(
    conn: JamoviConnection,
    analysis_id: int,
) -> dict[str, Any]:
    """Get the results of a previously run analysis."""
    request = jcoms.AnalysisRequest()
    request.instanceId = conn.instance_id
    request.analysisId = analysis_id
    request.perform = jcoms.AnalysisRequest.Perform.RENDER

    payload = await conn.send(request, payload_type="AnalysisRequest")
    response = jcoms.AnalysisResponse()
    response.ParseFromString(payload)

    return {
        "analysisId": response.analysisId,
        "name": response.name,
        "ns": response.ns,
        "status": response.status,
        "hasResults": response.HasField("results"),
        "results": _results_to_dict(response.results) if response.HasField("results") else None,
        "error": (
            {"message": response.error.message}
            if response.HasField("error") and response.error.message
            else None
        ),
    }


async def jamovi_export_results(
    conn: JamoviConnection,
    analysis_id: int,
    part: str = "",
    fmt: str = "txt",
) -> dict[str, Any]:
    """Export analysis results in a specific format."""
    request = jcoms.AnalysisRequest()
    request.instanceId = conn.instance_id
    request.analysisId = analysis_id
    request.perform = jcoms.AnalysisRequest.Perform.SAVE
    request.part = part
    request.format = fmt

    payload = await conn.send(request, payload_type="AnalysisRequest")
    response = jcoms.AnalysisResponse()
    response.ParseFromString(payload)

    result: dict[str, Any] = {
        "analysisId": response.analysisId,
        "status": response.status,
    }

    if response.HasField("results"):
        result["results"] = _results_to_dict(response.results)

    return result
