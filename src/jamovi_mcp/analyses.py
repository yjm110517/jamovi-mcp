"""Analysis registry: discover available analyses and their option schemas."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def _find_module_dirs(jamovi_home: Path) -> list[Path]:
    modules_path = jamovi_home / "Resources" / "modules"
    if not modules_path.exists():
        return []
    return sorted(
        d for d in modules_path.iterdir()
        if d.is_dir() and (d / "jamovi.yaml").exists()
    )


def _load_module_meta(module_dir: Path) -> dict[str, Any] | None:
    yaml_path = module_dir / "jamovi.yaml"
    if not yaml_path.exists():
        return None
    with open(yaml_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _load_analysis_options(module_dir: Path, name: str) -> list[dict[str, Any]]:
    a_yaml = module_dir / "analyses" / f"{name}.a.yaml"
    if not a_yaml.exists():
        return []
    with open(a_yaml, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data.get("options", [])


def _describe_option(opt: dict[str, Any]) -> dict[str, Any]:
    desc: dict[str, Any] = {
        "name": opt.get("name", ""),
        "title": opt.get("title", ""),
        "type": opt.get("type", "String"),
    }
    if "default" in opt:
        desc["default"] = opt["default"]
    if "options" in opt:
        desc["choices"] = [
            o if isinstance(o, str) else o.get("name", o)
            for o in opt["options"]
        ]
    if "min" in opt:
        desc["min"] = opt["min"]
    if "max" in opt:
        desc["max"] = opt["max"]
    if "suggested" in opt:
        desc["suggested"] = opt["suggested"]
    if "permitted" in opt:
        desc["permitted"] = opt["permitted"]
    return desc


def build_registry(jamovi_home: Path | None = None) -> dict[str, Any]:
    """Build a registry of all available analyses and their options.

    Returns a dict mapping "ns/name" to analysis metadata.
    """
    if jamovi_home is None:
        from .config import JAMOVI_HOME
        jamovi_home = JAMOVI_HOME

    registry: dict[str, Any] = {}

    for module_dir in _find_module_dirs(jamovi_home):
        meta = _load_module_meta(module_dir)
        if meta is None:
            continue
        ns = meta.get("name", "")
        analyses = meta.get("analyses", [])
        if not isinstance(analyses, list):
            continue

        for analysis in analyses:
            name = analysis.get("name", "")
            key = f"{ns}/{name}"
            options = _load_analysis_options(module_dir, name)
            registry[key] = {
                "name": name,
                "ns": ns,
                "title": analysis.get("title", name),
                "menuGroup": analysis.get("menuGroup", ""),
                "menuTitle": analysis.get("menuTitle", ""),
                "description": analysis.get("description", ""),
                "options": [_describe_option(o) for o in options],
            }

    return registry


_ANALYSIS_REGISTRY: dict[str, Any] | None = None


def get_registry() -> dict[str, Any]:
    global _ANALYSIS_REGISTRY
    if _ANALYSIS_REGISTRY is None:
        _ANALYSIS_REGISTRY = build_registry()
    return _ANALYSIS_REGISTRY


def list_analyses() -> list[dict[str, Any]]:
    """Return a flat list of all available analyses."""
    registry = get_registry()
    result: list[dict[str, Any]] = []
    for key, info in registry.items():
        result.append({
            "id": key,
            "name": info["name"],
            "ns": info["ns"],
            "title": info["title"],
            "menuGroup": info["menuGroup"],
            "menuTitle": info["menuTitle"],
            "description": (
                info["description"][:200] if info["description"] else ""
            ),
        })
    result.sort(key=lambda a: (a["menuGroup"], a["menuTitle"]))
    return result


def get_analysis_options(ns: str, name: str) -> dict[str, Any] | None:
    """Get the full options schema for a specific analysis."""
    key = f"{ns}/{name}"
    return get_registry().get(key)
