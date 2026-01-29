from __future__ import annotations

import json
import logging
from typing import Any

from forge.execution import ExecutionContext
from temporalio import activity

from clark_protos.processors.customWorkflow_pb2 import (
    ProcessorCustomWorkflowConfig as CustomWorkflowConfig,
)
from clark_protos.processors.customWorkflow_pb2 import (
    ProcessorCustomWorkflowOutput as CustomWorkflowOutput,
)
from clark_protos.processors.questionAnswering_pb2 import Question
from clark_protos.processors.workflow_context_pb2 import WorkflowContext
from flow.flow_loader import FlowLoader
from flow.io_mapping import InputMapper, OutputMapper

_logger = activity.LoggerAdapter(logging.getLogger(__name__), None)


class CustomWorkflowActivity:
    """Temporal activity that runs Forge flows for CustomWorkflow processing."""

    _flow_loader: FlowLoader

    def __init__(self) -> None:
        self._flow_loader = FlowLoader()

    @activity.defn
    async def process(
        self,
        ctx: WorkflowContext,
        task_config: CustomWorkflowConfig,
    ) -> CustomWorkflowOutput:
        """Main activity entry - runs a Forge flow.

        Supports:
          - task_config.workflow_id (named flow)
          - task_config.additional_inputs (inline flow JSON or params)
          - fallback to default 'qa_default' flow
        """
        _logger.info(
            "CustomWorkflowActivity.process(job_id=%s) with workflow_id=%s",
            ctx.id,
            task_config.workflow_id or "qa_default",
        )
        _logger.info(
            "  - first_source_files: %d, second_source_files: %d, questions: %d",
            len(task_config.first_source_files),
            len(task_config.second_source_files),
            len(task_config.questions),
        )

        # 1) Resolve flow (inline vs named)
        flow_dict, additional_params = self._resolve_flow_and_params(task_config)

        # 2) Build flow inputs with custom workflow convention
        flow_inputs = InputMapper.build_custom_workflow_inputs(
            first_source_files=list(task_config.first_source_files),
            second_source_files=list(task_config.second_source_files),
            questions=list(task_config.questions),
            additional_params=additional_params,
        )

        # 3) Prepare authentication headers and execution context
        elise_api_headers = dict(ctx.headers) if ctx.headers else {}
        _logger.info("Authentication headers available: %s", list(elise_api_headers.keys()))

        execution_context = ExecutionContext(
            run_id=f"custom-workflow-{ctx.id}",
            elise_api_headers=elise_api_headers,
        )

        # 4) Execute flow with TemporalRuntime
        # Import here to avoid circular dependencies and ensure forge_tools are loaded
        try:
            from forge.execution.runtime import TemporalRuntime
            from forge.models import Flow
            from forge_tools.populated_registry import registry as forge_registry

            _logger.info("Using registry with %d tools", len(forge_registry._functions))
        except ImportError as e:
            _logger.error("Failed to import forge components: %s", e)
            _logger.error("Make sure forge and forge_tools are installed")
            error_msg = f"Failed to import forge components: {e}"
            raise RuntimeError(error_msg) from e

        # Convert flow dict to Flow object (Pydantic model)
        flow = Flow(**flow_dict)

        runtime = TemporalRuntime(registry=forge_registry)
        try:
            result = await runtime.run(
                flow=flow,
                inputs=flow_inputs,
                execution_context=execution_context,
            )
        except Exception as e:
            _logger.exception("Forge flow execution failed: %s", e)
            error_msg = f"Forge flow execution failed: {e}"
            raise RuntimeError(error_msg) from e
        finally:
            await runtime.cleanup()

        _logger.info(
            "Forge flow %s completed with status %s",
            flow.flow_id,
            result.status,
        )

        if result.status != "succeeded":
            error_msg = f"Forge flow failed with status {result.status}: {result.error}"
            _logger.error(error_msg)
            raise RuntimeError(error_msg)

        # 5) Map outputs to QuestionAnswer list
        answers = OutputMapper.to_question_answers(
            flow_outputs=result.outputs,
            original_questions=list[Question](task_config.questions),
        )

        return CustomWorkflowOutput(answers=answers)

    def _resolve_flow_and_params(
        self,
        cfg: CustomWorkflowConfig,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Determine which Flow to use and extract additional params.

        Priority:
        1. Inline flow in additional_inputs (JSON with 'flow_id', 'steps', etc.)
        2. Named flow via workflow_id
        3. Default flow (qa_default)

        Returns
        -------
            (flow_dict, additional_params)
        """
        additional_params: dict[str, Any] = {}

        # Parse additional_inputs
        if cfg.additional_inputs:
            try:
                data = json.loads(cfg.additional_inputs)
                _logger.info("Parsed additional_inputs: %s", data)

                # Detect if it's an inline flow (has flow_id and steps)
                if "flow_id" in data and "steps" in data:
                    _logger.info("Using inline flow from additional_inputs")
                    return data, {}

                # Otherwise, treat as additional params
                additional_params = data
                _logger.info("Using additional_inputs as params: %s", additional_params)
            except json.JSONDecodeError as e:
                _logger.error("Failed to parse additional_inputs as JSON: %s", e)

        # Use workflow_id or default
        flow_name = cfg.workflow_id or "qa_default"
        _logger.info("Loading named flow: %s", flow_name)
        flow_dict = self._flow_loader.load_by_name(flow_name)

        return flow_dict, additional_params
