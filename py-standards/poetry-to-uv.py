# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "tomlkit",
# ]
# ///

import re
import sys
from typing import Any

import tomlkit


def parse_authors(authors: list[str]):
    res = []
    for author in authors:
        name_email_pattern = r"^([\w\s]+)\s+<([^@]+@[^>]+)>$"
        match = re.match(name_email_pattern, author)
        if match:
            name = match.group(1)
            email = match.group(2)
            res.append({"name": name, "email": email})
    return res


def get_pyton_version(pyproject):
    if "requires-python" in pyproject.get("project", {}):
        return pyproject["project"]["requires-python"]

    dependencies = pyproject["tool"]["poetry"]["dependencies"]
    version = dependencies.get("python", "3.11.9")
    bound = parse_version(version)

    return f"{bound}".strip()


def parse_version(version: str) -> str:
    uv_bounds = []
    bounds = version.split(",")

    for bound in bounds:
        if bound.startswith("^"):
            uv_bounds.append(f">={bound[1:]}")
        elif bound.startswith("<"):
            uv_bounds.append(bound)
        elif bound == "*":
            continue
        else:
            uv_bounds.append(f"=={bound}")

    return ", ".join(uv_bounds)


def parse_dependencies(
    dependencies_dict: dict[str, Any],
    skip_optional: bool = True,
) -> list[str]:
    """Parse dependencies.

    Returns project.dependencies and tool.uv.sources
    """
    dependencies = []
    for dep, opt in dependencies_dict.items():
        if dep == "python":
            continue

        if isinstance(opt, str):
            version = opt
        else:
            if opt.get("optional") and skip_optional:
                continue

            version = opt.get("version")

        bounds = parse_version(version)

        extras = f'[{",".join(opt["extras"])}]' if isinstance(opt, dict) and "extras" in opt else ""

        dependencies.append(f"{dep}{extras} {bounds}".strip())

    return dependencies


def parse_dependency_groups(group) -> dict[str, Any]:
    dependency_groups = {}

    for name, opt in group.items():
        group_deps = parse_dependencies(opt["dependencies"])
        dependency_groups[name] = group_deps

    return dependency_groups


def parse_sources(source_list: list[dict[str, Any]]):
    indexes = []
    for source in source_list:
        if source["name"] == "PyPI":
            continue
        indexes.append(
            {
                "name": source["name"],
                "url": source["url"],
            },
        )
    return indexes


def parse_extras(
    dependencies_dict: dict[str, Any],
    extras: dict[str, list[str]],
) -> dict[str, list[str]]:
    res = {}
    parsed_dependencies = parse_dependencies(
        dependencies_dict=dependencies_dict,
        skip_optional=False,
    )

    def find_dep(dep_name: str) -> str:
        for dep in parsed_dependencies:
            if dep_name in dep.split()[0]:
                return dep

        raise ValueError(f"{dep_name} not found in {parsed_dependencies}")

    for extra_name, extra_list in extras.items():
        res[extra_name] = [find_dep(dep) for dep in extra_list]

    return res


def parse_other_tools(pyproject):
    return {
        tool_name: tool_config
        for tool_name, tool_config in pyproject.get("tool", {}).items()
        if tool_name != "poetry"
    }


def parse_poe_tasks(poe_tasks: dict[str, str]):
    res = {}
    for task_name, task in poe_tasks.items():
        if isinstance(task, str):
            if "coverage" in task:
                task = task.replace("coverage", "uv run coverage")
                res[task_name] = task
                continue
            if "pytest" in task:
                task = task.replace("pytest", "uv run pytest")
                res[task_name] = task
                continue
            if "poetry run python -m" in task:
                task = task.replace("poetry run python -m", "uv run")
            if "poetry run" in task:
                task = task.replace("poetry run", "uv run")
            if "python -m" in task:
                task = task.replace("python -m", "uv run")
            if "python" in task:
                task = task.replace("python", "uv run")

        res[task_name] = task
    return res


def main(file_name) -> None:
    with open(file_name) as f:
        pyproject_str = f.read()
        pyproject = tomlkit.parse(pyproject_str)

    with open(f"{file_name}.bak", "w") as f:
        f.write(pyproject_str)

    poetry: dict[str, Any] = pyproject["tool"]["poetry"]

    uv_pyproject_dict = {
        "project": {
            "name": poetry.get("name", "unknown"),
            "version": poetry.get("version", "unknown"),
            "description": poetry.get("description", "unknown"),
            "readme": poetry.get("readme", "README.md"),
            "authors": parse_authors(poetry.get("authors", [])),
            "requires-python": get_pyton_version(pyproject),
            "classifiers": ["Private :: Do Not Upload"],
        },
    }

    dependencies = parse_dependencies(poetry["dependencies"])
    uv_pyproject_dict["project"]["dependencies"] = dependencies
    uv_pyproject_dict["project"]["optional-dependencies"] = parse_extras(
        poetry["dependencies"],
        poetry.get("extras", {}),
    )

    if dependency_groups := parse_dependency_groups(poetry.get("group", {})):
        uv_pyproject_dict["dependency-groups"] = dependency_groups

    if index := parse_sources(source_list=poetry.get("source", [])):
        uv_pyproject_dict.setdefault("tool", {}).setdefault("uv", {})["index"] = index

    if other_tools := parse_other_tools(pyproject=pyproject):
        uv_pyproject_dict.setdefault("tool", {}).update(other_tools)

    if "version" in pyproject["tool"]:
        uv_pyproject_dict.setdefault("tool", {}).setdefault("bumpversion", {}).update(
            {
                "current_version": uv_pyproject_dict["project"]["version"],
                "parse": r"(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)",
                "serialize": ["{major}.{minor}.{patch}"],
                "search": "{current_version}",
                "replace": "{new_version}",
                "regex": False,
                "ignore_missing_version": False,
                "ignore_missing_files": False,
                "tag": True,
                "sign_tags": False,
                "tag_name": "pypi-{new_version}",
                "tag_message": "chore(release): bump version from {current_version} → {new_version}",
                "allow_dirty": False,
                "commit": True,
                "message": "chore(release): bump version from {current_version} → {new_version}",
                "commit_args": "",
                "setup_hooks": [],
                "pre_commit_hooks": [],
                "post_commit_hooks": [],
                "files": [
                    {
                        "filename": "pyproject.toml",
                        "search": 'version = "{current_version}"',
                        "replace": 'version = "{new_version}"',
                    },
                ],
            },
        )

    if "poe" in pyproject["tool"]:
        updated_task = parse_poe_tasks(pyproject["tool"]["poe"]["tasks"])
        uv_pyproject_dict.setdefault("tool", {}).setdefault("poe", {}).setdefault(
            "tasks",
            {},
        ).update(updated_task)

    uv_pyproject_dict["build-system"] = {
        "requires": ["hatchling"],
        "build-backend": "hatchling.build",
    }

    with open(file_name, "w") as f:
        f.write(tomlkit.dumps(uv_pyproject_dict))


if __name__ == "__main__":
    main(sys.argv[1])
