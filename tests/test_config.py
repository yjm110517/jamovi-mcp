from __future__ import annotations

from pathlib import Path

from jamovi_mcp.config import (
    find_jamovi_home,
    jamovi_version_key,
    read_jamovi_env,
    validate_jamovi_home,
)
from jamovi_mcp.engine import EngineManager


def _make_install(root: Path, name: str, version: str, r_version: str = "4.4.1") -> Path:
    home = root / name
    (home / "Frameworks" / "python").mkdir(parents=True)
    (home / "Frameworks" / "R").mkdir(parents=True)
    (home / "Resources" / "server").mkdir(parents=True)
    (home / "Resources" / "modules" / "base" / "R").mkdir(parents=True)
    (home / "Resources" / "client").mkdir(parents=True)
    (home / "Resources" / "i18n").mkdir(parents=True)
    (home / "Resources" / "lib").mkdir(parents=True)
    (home / "bin").mkdir(parents=True)
    (home / "Frameworks" / "python" / "python.exe").touch()
    (home / "Frameworks" / "R" / f"README.R-{r_version}").touch()
    (home / "Resources" / "version").write_text(version, encoding="utf-8")
    return home


def test_find_jamovi_home_prefers_env_var(monkeypatch, tmp_path) -> None:
    selected = tmp_path / "custom jamovi"

    monkeypatch.setenv("JAMOVI_HOME", str(selected))

    assert find_jamovi_home() == selected


def test_find_jamovi_home_selects_highest_installed_version(
    monkeypatch,
    tmp_path,
) -> None:
    old_home = _make_install(tmp_path, "jamovi 98.0.0.0", "98.0.0.0")
    new_home = _make_install(tmp_path, "jamovi 99.0.0.0", "99.0.0.0")

    monkeypatch.delenv("JAMOVI_HOME", raising=False)
    monkeypatch.setenv("ProgramFiles", str(tmp_path))
    monkeypatch.setenv("ProgramW6432", str(tmp_path))
    monkeypatch.setenv("ProgramFiles(x86)", str(tmp_path))

    assert find_jamovi_home() == new_home
    assert jamovi_version_key(new_home) > jamovi_version_key(old_home)


def test_read_jamovi_env_resolves_env_conf_paths(tmp_path) -> None:
    home = _make_install(tmp_path, "jamovi 3.0.0.0", "3.0.0.0")
    (home / "bin" / "env.conf").write_text(
        "\n".join([
            "[ENV]",
            r"R_HOME=..\Frameworks\R",
            r"R_LIBS=..\Resources\modules\base\R",
            r"PATH=.;..\bin;..\Resources\lib",
            r"JAMOVI_HOME=..",
            r"JAMOVI_MODULES_PATH=../Resources/modules",
            "JAMOVI_R_VERSION=5.1.0-x64",
        ]),
        encoding="utf-8",
    )

    env = read_jamovi_env(home)

    assert env["JAMOVI_HOME"] == str(home.resolve())
    assert env["R_HOME"] == str((home / "Frameworks" / "R").resolve())
    assert env["JAMOVI_MODULES_PATH"] == str(
        (home / "Resources" / "modules").resolve()
    )
    assert env["JAMOVI_R_VERSION"] == "5.1.0-x64"
    assert str((home / "bin").resolve()) in env["PATH"]
    assert str((home / "Resources" / "lib").resolve()) in env["PATH"]


def test_engine_uses_selected_jamovi_home_and_env_conf(tmp_path) -> None:
    home = _make_install(tmp_path, "jamovi 4.0.0.0", "4.0.0.0")
    (home / "bin" / "env.conf").write_text(
        "\n".join([
            "[ENV]",
            r"R_HOME=..\Frameworks\R",
            r"PATH=.;..\bin",
            r"JAMOVI_HOME=..",
            "JAMOVI_R_VERSION=6.0.0-x64",
        ]),
        encoding="utf-8",
    )

    engine = EngineManager(jamovi_home=home)
    env = engine._build_env()

    assert engine.jamovi_home == validate_jamovi_home(home)
    assert env["JAMOVI_HOME"] == str(home.resolve())
    assert env["R_HOME"] == str((home / "Frameworks" / "R").resolve())
    assert env["JAMOVI_R_VERSION"] == "6.0.0-x64"
