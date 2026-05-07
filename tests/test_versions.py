from pathlib import Path

import yaml


def _read_project_version(pyproject_path: Path) -> str:
    in_project_section = False
    for raw_line in pyproject_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()

        if line.startswith("[") and line.endswith("]"):
            in_project_section = line == "[project]"
            continue

        if in_project_section and line.startswith("version"):
            # example: version = "0.1.0"
            _, value = line.split("=", 1)
            return value.strip().strip('"').strip("'")

    raise AssertionError("Cannot find [project].version in pyproject.toml")


def test_pyproject_version_matches_plugin_yaml(repo_root: Path):
    pyproject_path = repo_root / "pyproject.toml"
    plugin_yaml_path = repo_root / "hermes_jobctl" / "plugin.yaml"

    project_version = _read_project_version(pyproject_path)
    plugin_version = str(
        yaml.safe_load(plugin_yaml_path.read_text(encoding="utf-8"))["version"]
    )

    assert project_version == plugin_version, (
        f"Version mismatch: pyproject.toml={project_version}, "
        f"hermes_jobctl/plugin.yaml={plugin_version}"
    )
