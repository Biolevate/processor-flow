"""Verify that the processor-flow setup is correct."""

import sys
from pathlib import Path


def check_imports():
    """Verify all required modules can be imported."""
    print("🔍 Checking imports...")

    try:
        from flow.default_flows import build_qa_default_flow
        print("  ✅ flow.default_flows")
    except ImportError as e:
        print(f"  ❌ flow.default_flows: {e}")
        return False

    try:
        from flow.activity import ForgeActivity
        print("  ✅ flow.activity")
    except ImportError as e:
        print(f"  ❌ flow.activity: {e}")
        return False

    try:
        from flow.io_mapping import InputMapper, OutputMapper
        print("  ✅ flow.io_mapping")
    except ImportError as e:
        print(f"  ❌ flow.io_mapping: {e}")
        return False

    try:
        import forge_tools.populated_registry
        print("  ✅ forge_tools.populated_registry")
    except ImportError as e:
        print(f"  ❌ forge_tools.populated_registry: {e}")
        print("     Note: This is expected if forge_tools is not installed")
        return True  # Non-blocking for now

    return True


def check_flow_loader():
    """Verify the FlowLoader can load flows transparently."""
    print("\n🔍 Checking FlowLoader...")

    try:
        from flow.flow_loader import FlowLoader

        loader = FlowLoader()
        print(f"  ✅ FlowLoader initialized with dir: {loader._flows_dir}")

        # List available flows
        available = loader._list_available_flows()
        if available:
            print(f"  📝 Available flows: {', '.join(available)}")

        # Try loading qa_default
        flow_dict = loader.load_by_name("qa_default")
        print(f"  ✅ Loaded qa_default: {flow_dict['flow_id']}")
        print(f"  ✅ Number of steps: {len(flow_dict['steps'])}")

        # Verify flow structure
        assert flow_dict["flow_id"] == "qa_default", "Flow ID should be 'qa_default'"
        assert len(flow_dict["steps"]) == 3, "Should have 3 steps"

        print("  ✅ FlowLoader working correctly")
        return True

    except Exception as e:
        print(f"  ❌ Error with FlowLoader: {e}")
        import traceback
        traceback.print_exc()
        return False


def check_flow_files():
    """Verify flow files exist (Python and/or JSON)."""
    print("\n🔍 Checking flow files...")

    flows_dir = Path(__file__).parent.parent / "resources" / "forge_flows"

    # Check for qa_default (Python or JSON)
    py_path = flows_dir / "qa_default.py"
    json_path = flows_dir / "qa_default.json"

    has_py = py_path.exists()
    has_json = json_path.exists()

    if has_py:
        print(f"  ✅ Python flow exists: {py_path.name}")
    if has_json:
        print(f"  ✅ JSON flow exists: {json_path.name}")

    if not has_py and not has_json:
        print("  ❌ No qa_default flow found (.py or .json)")
        print("     Create qa_default.py or run: uv run python scripts/generate_default_flow.py")
        return False

    # Verify Python flow if it exists
    if has_py:
        try:
            from flow.flow_loader import FlowLoader
            loader = FlowLoader()
            flow_dict = loader.load_by_name("qa_default")

            assert flow_dict["flow_id"] == "qa_default", "Flow ID should be 'qa_default'"
            assert len(flow_dict["steps"]) == 3, "Should have 3 steps"

            print("  ✅ Python flow is valid and loadable")
            return True

        except Exception as e:
            print(f"  ❌ Error loading Python flow: {e}")
            return False

    # Verify JSON flow if it exists (and no Python)
    if has_json and not has_py:
        import json
        try:
            with json_path.open() as f:
                flow_dict = json.load(f)

            assert flow_dict["flow_id"] == "qa_default", "Flow ID in JSON should be 'qa_default'"
            assert len(flow_dict["steps"]) == 3, "JSON should have 3 steps"

            print(f"  ✅ JSON flow is valid: {flow_dict['flow_id']} with {len(flow_dict['steps'])} steps")
            return True

        except Exception as e:
            print(f"  ❌ Error reading JSON: {e}")
            return False

    return True


def check_registry():
    """Check if subflows are registered."""
    print("\n🔍 Checking forge registry...")

    try:
        from forge_tools.populated_registry import registry

        required_subflows = [
            "fits_in_single_call_flow",
            "qa_agent_flow",
            "qa_agent_flow_with_full_content",
        ]

        registered = list(registry._functions.keys())
        print(f"  📝 Total registered functions: {len(registered)}")

        missing = []
        for subflow in required_subflows:
            if subflow in registered:
                print(f"  ✅ {subflow}")
            else:
                print(f"  ❌ {subflow} (not found)")
                missing.append(subflow)

        if missing:
            print(f"\n  ⚠️  Missing subflows: {missing}")
            print("     These subflows are required by qa_default flow")
            return False

        return True

    except ImportError:
        print("  ⚠️  Could not import forge_tools.populated_registry")
        print("     Make sure forge_tools is installed")
        return True  # Non-blocking


def check_test_flow():
    """Verify test_simple flow exists for backwards compatibility."""
    print("\n🔍 Checking test flow...")

    test_path = Path(__file__).parent.parent / "resources" / "forge_flows" / "test_simple.json"

    if test_path.exists():
        print("  ✅ test_simple.json exists (backwards compatibility)")
        return True
    print("  ⚠️  test_simple.json not found")
    print("     This is OK if you don't need the test flow")
    return True


def main():
    print("=" * 60)
    print("Processor-Flow Setup Verification")
    print("=" * 60)

    checks = [
        ("Imports", check_imports),
        ("FlowLoader", check_flow_loader),
        ("Flow Files", check_flow_files),
        ("Test Flow", check_test_flow),
        ("Forge Registry", check_registry),
    ]

    results = {}
    for name, check_fn in checks:
        try:
            results[name] = check_fn()
        except Exception as e:
            print(f"\n❌ Unexpected error in {name}: {e}")
            results[name] = False

    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)

    for name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {name}")

    all_passed = all(results.values())

    if all_passed:
        print("\n🎉 All checks passed! Setup is complete.")
        print("\nNext steps:")
        print("  1. Run tests: uv run python scripts/run_temporal_task.py")
        print("  2. Deploy to production with FORGE_FLOWS_DIR=/opt/forge_flows")
        return 0
    print("\n⚠️  Some checks failed. Please review the errors above.")
    return 1


if __name__ == "__main__":
    sys.exit(main())

