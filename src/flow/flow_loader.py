"""Flow loader for Forge flows."""

import importlib.util
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class FlowLoader:
    """Load Forge Flows from Python or JSON files transparently."""

    def __init__(self, flows_dir: str | Path | None = None) -> None:
        # Try FORGE_FLOWS_DIR env var, then local resources, then default
        if flows_dir:
            self._flows_dir = Path(flows_dir)
        elif env_dir := os.getenv("FORGE_FLOWS_DIR"):
            self._flows_dir = Path(env_dir)
        else:
            # Try local resources directory for development
            local_resources = Path(__file__).parent.parent.parent / "resources" / "forge_flows"
            if local_resources.exists():
                self._flows_dir = local_resources
                logger.info("Using local resources directory: %s", self._flows_dir)
            else:
                self._flows_dir = Path("/opt/forge_flows")

        self._cache: dict[str, dict[str, Any]] = {}

    def load_by_name(self, flow_name: str) -> dict[str, Any]:
        """Load a flow by name - auto-detects .py or .json format.
        
        Priority:
        1. {flow_name}.py  - Python module with build_flow() function
        2. {flow_name}.json - JSON file
        """
        if flow_name in self._cache:
            return self._cache[flow_name]

        # Try Python first
        py_path = self._flows_dir / f"{flow_name}.py"
        if py_path.exists():
            flow_dict = self._load_python_flow(py_path, flow_name)
            self._cache[flow_name] = flow_dict
            return flow_dict

        # Try JSON
        json_path = self._flows_dir / f"{flow_name}.json"
        if json_path.exists():
            flow_dict = self._load_json_flow(json_path, flow_name)
            self._cache[flow_name] = flow_dict
            return flow_dict

        # Not found - list available flows
        available = self._list_available_flows()
        msg = (
            f"Flow '{flow_name}' not found in {self._flows_dir}. "
            f"Available flows: {available}"
        )
        raise FileNotFoundError(msg)

    def _load_python_flow(self, path: Path, flow_name: str) -> dict[str, Any]:
        """Load a flow from a Python module."""
        logger.info("Loading Python flow '%s' from %s", flow_name, path)

        # Import the module dynamically
        spec = importlib.util.spec_from_file_location(f"flow_{flow_name}", path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load module from {path}")

        module = importlib.util.module_from_spec(spec)
        sys.modules[f"flow_{flow_name}"] = module
        spec.loader.exec_module(module)

        # Call the standard build_flow() function
        if not hasattr(module, "build_flow"):
            raise AttributeError(
                f"Python flow '{flow_name}' must define a build_flow() function",
            )

        flow = module.build_flow()

        # Convert Flow object to dict (if Pydantic model)
        if hasattr(flow, "model_dump"):
            return flow.model_dump()
        if isinstance(flow, dict):
            return flow
        raise TypeError(
            f"build_flow() must return a Flow object or dict, got {type(flow)}",
        )

    def _load_json_flow(self, path: Path, flow_name: str) -> dict[str, Any]:
        """Load a flow from a JSON file."""
        logger.info("Loading JSON flow '%s' from %s", flow_name, path)
        with path.open() as f:
            return json.load(f)

    def _list_available_flows(self) -> list[str]:
        """List all available flow names (both .py and .json)."""
        flows = set()
        if self._flows_dir.exists():
            for p in self._flows_dir.glob("*.py"):
                if p.stem != "__init__":
                    flows.add(f"{p.stem} (py)")
            for p in self._flows_dir.glob("*.json"):
                flows.add(f"{p.stem} (json)")
        return sorted(flows)

    def load_from_json(self, flow_json: str) -> dict[str, Any]:
        """Parse a Flow from inline JSON text."""
        try:
            return json.loads(flow_json)
        except json.JSONDecodeError as e:
            msg = f"Invalid flow JSON: {e}"
            raise ValueError(msg) from e
        except Exception as e:
            msg = f"Invalid flow definition: {e}"
            raise ValueError(msg) from e

