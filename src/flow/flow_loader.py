"""Flow loader for Forge flows."""

import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class FlowLoader:
    """Load Forge Flows from JSON files or inline JSON."""

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
        """Load a flow '<flow_name>.json' from the flows directory."""
        if flow_name in self._cache:
            return self._cache[flow_name]

        path = self._flows_dir / f"{flow_name}.json"
        if not path.exists():
            available = [
                p.stem for p in self._flows_dir.glob("*.json") if p.is_file()
            ]
            msg = (
                f"Flow '{flow_name}' not found at {path}. "
                f"Available flows: {available}"
            )
            raise FileNotFoundError(msg)

        logger.info("Loading flow '%s' from %s", flow_name, path)
        with path.open() as f:
            self._cache[flow_name] = json.load(f)

        return self._cache[flow_name]

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

