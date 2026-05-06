"""Configuration and jamovi installation discovery."""

from __future__ import annotations

import configparser
import os
import re
from pathlib import Path

DEFAULT_JAMOVI_HOME = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "jamovi"


class ConfigError(RuntimeError):
    """Raised when the local jamovi installation cannot be used."""


def _dedupe_paths(paths: list[Path]) -> list[Path]:
    seen: set[str] = set()
    result: list[Path] = []
    for path in paths:
        key = str(path).lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(path)
    return result


def _program_files_roots() -> list[Path]:
    roots: list[Path] = []
    for name in ("ProgramFiles", "ProgramW6432", "ProgramFiles(x86)"):
        value = os.environ.get(name)
        if value:
            roots.append(Path(value))
    roots.extend([Path(r"C:\Program Files"), Path(r"C:\Program Files (x86)")])
    return _dedupe_paths(roots)


def _candidate_jamovi_homes() -> list[Path]:
    candidates: list[Path] = []
    for root in _program_files_roots():
        if not root.exists():
            continue
        candidates.extend(path for path in root.glob("jamovi*") if path.is_dir())
    return _dedupe_paths(candidates)


def _version_tuple_from_text(text: str) -> tuple[int, ...]:
    numbers = re.findall(r"\d+", text)
    if not numbers:
        return (0,)
    return tuple(int(number) for number in numbers)


def jamovi_version_key(jamovi_home: Path) -> tuple[int, ...]:
    """Return a sortable version key for a jamovi installation directory."""
    version_file = jamovi_home / "Resources" / "version"
    if version_file.exists():
        try:
            text = version_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""
        version = _version_tuple_from_text(text)
        if version != (0,):
            return version
    return _version_tuple_from_text(jamovi_home.name)


def is_jamovi_home(path: Path) -> bool:
    """Return True when a directory has the files needed to launch jamovi."""
    return (
        path.is_dir()
        and (path / "Frameworks" / "python" / "python.exe").exists()
        and (path / "Resources" / "server").is_dir()
        and (path / "Resources" / "modules").is_dir()
    )


def find_jamovi_home() -> Path:
    """Find the jamovi installation to use.

    JAMOVI_HOME wins when set. Otherwise, choose the highest installed jamovi
    version under the standard Program Files locations.
    """
    env_home = os.environ.get("JAMOVI_HOME")
    if env_home:
        return Path(env_home).expanduser()

    candidates = [path for path in _candidate_jamovi_homes() if is_jamovi_home(path)]
    if not candidates:
        return DEFAULT_JAMOVI_HOME

    return sorted(candidates, key=jamovi_version_key, reverse=True)[0]


def validate_jamovi_home(jamovi_home: Path) -> Path:
    """Validate and normalize the selected jamovi installation path."""
    path = jamovi_home.expanduser().resolve(strict=False)
    if is_jamovi_home(path):
        return path

    missing: list[str] = []
    checks = {
        "Frameworks\\python\\python.exe": path / "Frameworks" / "python" / "python.exe",
        "Resources\\server": path / "Resources" / "server",
        "Resources\\modules": path / "Resources" / "modules",
    }
    for label, target in checks.items():
        if not target.exists():
            missing.append(label)

    details = ", ".join(missing) if missing else "not a directory"
    raise ConfigError(
        f"Invalid JAMOVI_HOME: {path} ({details}). "
        "Set JAMOVI_HOME to the jamovi install directory that contains "
        "Frameworks and Resources."
    )


def _resolve_env_path(value: str, base_dir: Path) -> str:
    path = Path(value)
    if path.is_absolute():
        return str(path)
    return str((base_dir / path).resolve(strict=False))


def _resolve_env_path_list(value: str, base_dir: Path) -> str:
    parts = [part for part in value.split(";") if part]
    return os.pathsep.join(_resolve_env_path(part, base_dir) for part in parts)


def _default_jamovi_env(jamovi_home: Path) -> dict[str, str]:
    resources = jamovi_home / "Resources"
    frameworks = jamovi_home / "Frameworks"
    bin_dir = jamovi_home / "bin"
    env = {
        "R_HOME": str(frameworks / "R"),
        "R_LIBS": str(resources / "modules" / "base" / "R"),
        "JAMOVI_HOME": str(jamovi_home),
        "JAMOVI_MODULES_PATH": str(resources / "modules"),
        "JAMOVI_CLIENT_PATH": str(resources / "client"),
        "JAMOVI_I18N_PATH": str(resources / "i18n"),
        "JAMOVI_VERSION_PATH": str(resources / "version"),
    }
    readme_versions = sorted((frameworks / "R").glob("README.R-*"))
    if readme_versions:
        version = readme_versions[-1].name.removeprefix("README.R-")
        env["JAMOVI_R_VERSION"] = f"{version}-x64"
    env["PATH"] = os.pathsep.join([
        str(bin_dir),
        str(resources / "lib"),
        str(frameworks / "R" / "bin" / "x64"),
        str(frameworks / "R" / "library" / "RInside" / "lib" / "x64"),
    ])
    return env


def read_jamovi_env(jamovi_home: Path) -> dict[str, str]:
    """Read jamovi's own bin/env.conf and return absolute env values."""
    jamovi_home = jamovi_home.expanduser().resolve(strict=False)
    env = _default_jamovi_env(jamovi_home)
    env_conf = jamovi_home / "bin" / "env.conf"
    if not env_conf.exists():
        return env

    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str
    parser.read(env_conf, encoding="utf-8")
    if not parser.has_section("ENV"):
        return env

    bin_dir = env_conf.parent
    for key, value in parser.items("ENV"):
        if key == "JAMOVI_HOME":
            env[key] = str(jamovi_home)
        elif key == "PATH":
            env[key] = _resolve_env_path_list(value, bin_dir)
        elif key.endswith("_PATH") or key in {"R_HOME", "R_LIBS"}:
            env[key] = _resolve_env_path(value, bin_dir)
        else:
            env[key] = value
    return env


JAMOVI_HOME = find_jamovi_home()
JAMOVI_PORT: int = int(os.environ.get("JAMOVI_PORT", "0"))
