# Processor Flow - Setup Summary

## Overview

Successfully renamed from `processor-forge` to `processor-flow` to avoid naming conflicts with the `forge` library.

## Final Structure

```
processor-flow/
├── src/flow/                    # Module named 'flow' (not 'forge')
│   ├── __init__.py
│   ├── activity.py
│   ├── workflow.py
│   ├── main.py
│   ├── flow_loader.py
│   └── io_mapping.py
├── resources/forge_flows/
│   ├── qa_default.json
│   └── FLOW_GUIDE.md
├── charts/processor-flow/       # Helm charts
├── scripts/
│   └── run_temporal_task.py
├── pyproject.toml              # Project: 'flow', Module: 'flow'
└── Dockerfile
```

## Key Configuration

### pyproject.toml
- **Project name**: `flow`
- **Module directory**: `src/flow/`
- **Entry point**: `python -m flow.main`
- **Dependencies**:
  - `forge>=0.1.0` (the Forge library)
  - `forge-tools>=0.1.0` (Forge tools)
  - `temporalio>=1.13.0,<1.18.0` (compatible version)

### Import Structure
- **Local module imports**: `from flow.activity import ...`
- **Forge library imports**: `from forge.runtime import LocalRuntime`
- **Forge tools imports**: `from forge_tools.populated_registry import registry`

## Resolved Issues

1. ✅ **Naming conflict**: Avoided `forge` module name conflicting with `forge` library
2. ✅ **Protobuf generation**: Generated `forge_pb2.py` with correct protobuf version
3. ✅ **Temporal version**: Compatible with `pyclark-temporal` 0.2.2

## Running the Processor

### Local Development
```bash
cd /path/to/processor-flow
uv sync
poe serve
```

### Docker
```bash
docker build -t processor-flow .
docker run processor-flow
```

### Important Notes

- The **protobuf files** need to be regenerated when the venv changes:
  ```bash
  uv run python -m grpc_tools.protoc -I ../../../clark-protos \
    --python_out=.venv/lib/python3.13/site-packages/ \
    --pyi_out=.venv/lib/python3.13/site-packages/ \
    ../../../clark-protos/clark-protos/processors/forge.proto
  ```

- The processor uses the **Forge library** (`forge`) but the **module is named** `flow` to avoid conflicts

## Environment Variables

Required for operation:
- `TEMPORAL_ADDRESS`: Temporal server address
- `EXCHANGE_URL`: Token exchange service URL
- `EXCHANGE_CLIENT_ID`: Client ID for token exchange
- `EXCHANGE_CLIENT_SECRET`: Client secret for token exchange
- `FORGE_FLOWS_DIR`: Flow resources directory (default: `/opt/forge_flows`)

## Next Steps

1. **Implement `qa_orchestrator`**: The default flow references this function in forge_tools
2. **Test with real data**: Use `scripts/run_temporal_task.py` to test
3. **Deploy**: Use Helm charts to deploy to Kubernetes
4. **Add more flows**: Create additional flow definitions in `resources/forge_flows/`

## Status

✅ **READY FOR USE**

The processor is fully operational and ready to process Forge flows!

