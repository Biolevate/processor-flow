<p align="center">
    <img src="https://biolevate-statics.s3.eu-west-1.amazonaws.com/logo/SVG/Biolevate_azure.svg"
        height="130">
</p>
<p align="center">
<a href="https://github.com/Biolevate/processor-forge/actions/workflows/build.yml"><img src="https://github.com/Biolevate/processor-forge/actions/workflows/build.yml/badge.svg"></a>
</p>

# Biolevate Processor Flow

Processor Flow is a dynamic workflow processor that leverages the Forge library to execute configurable flows. It provides the same interface as the QuestionAnswering processor but with the flexibility to run any Forge flow.

## Features

- **Compatible with QuestionAnswering**: Accepts the same input/output format as the QuestionAnswering processor
- **Dynamic Flow Selection**: Choose flows at runtime via flow name or inline JSON
- **Hot-Reloadable Flows**: Add new flows without redeploying by mounting JSON files
- **Default QA Flow**: Includes a default flow that mimics QuestionAnswering behavior
- **Extensible**: Easy to add new flows and customize behavior

## Architecture

### Input Configuration

The processor accepts:
- `files`: List of FileMetaData (documents to process)
- `questions`: List of Questions to answer
- `flow_name`: Optional name of a flow resource to load (e.g., "qa_default")
- `flow_json`: Optional inline JSON definition of a Forge Flow
- `flow_params`: Optional generic parameters for flows

### Flow Loading

Flows are loaded from:
1. **Inline JSON** (`flow_json` parameter) - highest precedence
2. **Named flows** (`flow_name` parameter) - loaded from `FORGE_FLOWS_DIR`
3. **Default flow** - `qa_default` if nothing specified

Flow directory is configurable via `FORGE_FLOWS_DIR` environment variable (default: `/opt/forge_flows`).

### Components

- **FlowLoader**: Loads and caches Forge flows from JSON files or inline definitions
- **InputMapper**: Converts protobuf messages to Forge flow inputs
- **OutputMapper**: Converts Forge flow outputs back to QuestionAnswer protos
- **ForgeActivity**: Temporal activity that executes Forge flows
- **TemporalForgeWorkflow**: Temporal workflow for the processor

## Local Installation

**Prerequisites:**
- Python 3.13+
- uv (recommended) or pip

**Installation:**
```console
uv sync
source .venv/bin/activate
```

Run unit tests:
```console
poe test
```

Run the processor locally:
```console
poe serve
```

## Configuration

### Environment Variables

- `FORGE_FLOWS_DIR`: Directory containing flow JSON files (default: `/opt/forge_flows`)
- `TEMPORAL_ADDRESS`: Temporal server address
- `EXCHANGE_URL`: Token exchange service URL
- `EXCHANGE_CLIENT_ID`: Token exchange client ID
- `EXCHANGE_CLIENT_SECRET`: Token exchange client secret

### Flow Resources

Place flow JSON files in the `FORGE_FLOWS_DIR` directory with `.json` extension. The flow name is the filename without extension.

Example: `/opt/forge_flows/qa_default.json` → flow name `"qa_default"`

## Adding New Flows

1. Create a new JSON flow definition (see `resources/forge_flows/qa_default.json` for example)
2. Mount or copy it to `FORGE_FLOWS_DIR` in the container
3. Use the flow by setting `flow_name` in the processor config

No code changes or redeployment needed!

## Deployment

### Prerequisites

- Helm 3+
- aws-cli 2+

### AWS Login

```console
aws sso login --profile <my-profile>
```

### ECR Login

```console
aws ecr get-login-password \
     --region eu-west-1 | helm registry login \
     --username AWS \
     --password-stdin 396802430222.dkr.ecr.eu-west-1.amazonaws.com/processor-forge
```

### Install/Upgrade

```console
export platform_environment=<platform_environment>
helm upgrade --install processor-forge oci://396802430222.dkr.ecr.eu-west-1.amazonaws.com/processor-forge \
    --namespace ${platform_environment}-biolevate-apps \
    --set application.environment=${platform_environment} \
    --set application.name=processor-forge \
    --version <helm_version>
```

> *helm_version* can be found in the Chart.yaml file (key=version)

### Uninstall

```console
export platform_environment=<platform_environment>
helm delete processor-forge --namespace ${platform_environment}-biolevate-apps
```

## Development

The processor is structured as follows:

```
src/forge/
├── __init__.py          # Module exports
├── activity.py          # Forge activity implementation
├── workflow.py          # Temporal workflow definition
├── main.py             # Worker entry point
├── flow_loader.py      # Flow loading logic
└── io_mapping.py       # Input/output mapping utilities

resources/
└── forge_flows/
    └── qa_default.json # Default QA flow
```

## Future Enhancements

- **Temporal Runtime**: Switch from LocalRuntime to TemporalRuntime for distributed execution
- **Flow Validation**: Add schema validation for flow definitions
- **Flow Monitoring**: Enhanced observability for flow execution
- **Flow Versioning**: Support for versioned flows
