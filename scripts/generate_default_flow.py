"""Generate default flow JSON from Python definition."""

import json
from pathlib import Path

from flow.default_flows import build_qa_default_flow


def main():
    flow = build_qa_default_flow()
    flow_dict = flow.model_dump()

    # Output to resources directory
    resources_dir = Path(__file__).parent.parent / "resources" / "forge_flows"
    resources_dir.mkdir(parents=True, exist_ok=True)

    output_path = resources_dir / "qa_default.json"
    output_path.write_text(json.dumps(flow_dict, indent=2))
    
    print(f"✅ Generated {output_path}")
    print(f"   Flow ID: {flow_dict['flow_id']}")
    print(f"   Steps: {len(flow_dict['steps'])}")


if __name__ == "__main__":
    main()

