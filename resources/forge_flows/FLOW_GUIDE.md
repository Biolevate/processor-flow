# Forge Flow Guide

This directory contains Forge flow definitions that can be used by Processor Forge.

## Flow Structure

A Forge flow is a JSON file with the following structure:

```json
{
  "version": "1.0",
  "flow_id": "unique_flow_id",
  "name": "Human Readable Flow Name",
  "description": "Description of what this flow does",
  "inputs": {
    "parameters": {
      "param1": "type",
      "param2": "type"
    },
    "defaults": {}
  },
  "steps": [
    {
      "step_id": "step_1",
      "tasks": [
        {
          "task_id": "task_1",
          "function": "function_name",
          "inputs": {
            "input1": "$flow.param1",
            "input2": "literal_value"
          },
          "export_to_flow": true
        }
      ]
    }
  ]
}
```

## Standard Inputs for QA Flows

For Question Answering workflows, use these standard inputs:

```json
"inputs": {
  "parameters": {
    "file_ids": "list",
    "files": "list",
    "questions": "list"
  }
}
```

### File Structure

Each file in `files` is a dict with:
- `id`: File identifier
- `name`: File name
- `checksum`: File checksum
- `path`: File path
- `extension`: File extension
- `providerId`: Provider ID

### Question Structure

Each question in `questions` is a dict with:
- `id`: Question identifier
- `question`: The question text
- `answerType`: Expected answer type (int)
- `guidelines`: Guidelines for answering
- `expectedAnswer`: Expected answer (optional)
- `inputQuestionIds`: List of question IDs this depends on

## Standard Output for QA Flows

QA flows should export an `answers` list where each answer has:

```json
{
  "id": "question_id",
  "question": "original question",
  "expectedAnswer": "expected answer",
  "sourcedContent": "answer with citations",
  "explanation": "explanation or rationale",
  "answerValidity": 0.95,
  "validityExplanation": "why this answer is valid",
  "annotations": [],
  "inputQuestionIds": []
}
```

## Variable References

- `$flow.param_name`: Reference flow input parameter
- `$step.step_id.task_id`: Reference output from previous task

## Available Functions

Functions are registered in `forge_tools.populated_registry`. Common functions include:

### Search Functions
- `semantic_search`: Semantic search in documents
- `exact_search`: Exact keyword search

### Agent Functions
- `qa_orchestrator`: Question answering orchestrator with dependency handling
- `detailed_answer`: Generate detailed answer from context

### Text Processing
- `summarize`: Summarize text
- `extract_entities`: Extract named entities

## Example: Simple QA Flow

```json
{
  "version": "1.0",
  "flow_id": "simple_qa",
  "name": "Simple Question Answering",
  "description": "Basic QA without dependency handling",
  "inputs": {
    "parameters": {
      "file_ids": "list",
      "files": "list",
      "questions": "list"
    }
  },
  "steps": [
    {
      "step_id": "search",
      "tasks": [
        {
          "task_id": "semantic_search",
          "function": "semantic_search",
          "inputs": {
            "file_ids": "$flow.file_ids",
            "questions": "$flow.questions"
          }
        }
      ]
    },
    {
      "step_id": "answer",
      "tasks": [
        {
          "task_id": "generate_answers",
          "function": "detailed_answer",
          "inputs": {
            "questions": "$flow.questions",
            "search_results": "$step.search.semantic_search"
          },
          "export_to_flow": true
        }
      ]
    }
  ]
}
```

## Example: Multi-Step QA Flow

```json
{
  "version": "1.0",
  "flow_id": "multi_step_qa",
  "name": "Multi-Step Question Answering",
  "description": "QA with multiple processing steps",
  "inputs": {
    "parameters": {
      "file_ids": "list",
      "files": "list",
      "questions": "list"
    }
  },
  "steps": [
    {
      "step_id": "retrieve",
      "tasks": [
        {
          "task_id": "semantic_search",
          "function": "semantic_search",
          "inputs": {
            "file_ids": "$flow.file_ids",
            "questions": "$flow.questions"
          }
        },
        {
          "task_id": "exact_search",
          "function": "exact_search",
          "inputs": {
            "file_ids": "$flow.file_ids",
            "questions": "$flow.questions"
          }
        }
      ]
    },
    {
      "step_id": "process",
      "tasks": [
        {
          "task_id": "merge_results",
          "function": "merge_search_results",
          "inputs": {
            "semantic": "$step.retrieve.semantic_search",
            "exact": "$step.retrieve.exact_search"
          }
        }
      ]
    },
    {
      "step_id": "answer",
      "tasks": [
        {
          "task_id": "generate_answers",
          "function": "detailed_answer",
          "inputs": {
            "questions": "$flow.questions",
            "context": "$step.process.merge_results"
          },
          "export_to_flow": true
        }
      ]
    }
  ]
}
```

## Testing Flows

Test flows using the `run_temporal_task.py` script:

```python
ForgeRun(
    config=ProcessorForgeConfig(
        files=files,
        questions=questions,
        flow_name="your_flow_id",  # Name of the JSON file without .json
    ),
)
```

Or with inline JSON:

```python
ForgeRun(
    config=ProcessorForgeConfig(
        files=files,
        questions=questions,
        flow_json='{"version": "1.0", ...}',
    ),
)
```

## Flow Deployment

1. Create your flow JSON file: `my_flow.json`
2. Copy it to `FORGE_FLOWS_DIR` (default: `/opt/forge_flows`)
3. Reference it by name: `flow_name="my_flow"`

No processor restart needed! The FlowLoader will pick up the file on first use.

## Best Practices

1. **Use descriptive IDs**: Make flow_id, step_id, and task_id descriptive
2. **Export relevant outputs**: Use `export_to_flow: true` for outputs you need
3. **Handle errors**: Consider error handling in orchestrator functions
4. **Test incrementally**: Start with simple flows and add complexity
5. **Document your flows**: Add clear descriptions in the JSON
6. **Version your flows**: Use semantic versioning in flow_id when making breaking changes

## Troubleshooting

### Flow not found
- Check `FORGE_FLOWS_DIR` is set correctly
- Verify the JSON file exists: `/opt/forge_flows/your_flow.json`
- Check file permissions

### Invalid flow JSON
- Validate JSON syntax with a linter
- Check all required fields are present
- Verify function names exist in forge_tools registry

### Flow execution fails
- Check logs for detailed error messages
- Verify input parameters match expected types
- Ensure referenced functions are available
- Check variable references use correct syntax

