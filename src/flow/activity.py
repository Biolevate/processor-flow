from __future__ import annotations

import json
import logging
from typing import Any

from temporalio import activity

# Legacy forge proto (kept for reference)
# from clark_protos.processors.forge_pb2 import (
#     ProcessorForgeConfig as ForgeConfig,
#     ProcessorForgeOutput as ForgeOutput,
# )
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
            collection_id=task_config.collectionId if task_config.collectionId else None,
        )

        # 3) Prepare authentication for Forge tools
        # TODO: Forge and forge-tools need to be updated to support elise_api_headers
        # For now, we pass None as access_token since the new auth system uses headers
        # The headers from ctx contain X-Biolevate-Principal and X-Biolevate-Signature
        elise_api_headers = dict(ctx.headers)
        _logger.info("Authentication headers available: %s", list(elise_api_headers.keys()))
        _logger.warning(
            "Forge authentication not yet updated for new elise_api_headers system. "
            "Tools requiring Elise API access may fail until forge is updated."
        )

        # 4) Execute flow with LocalRuntime
        # Import here to avoid circular dependencies and ensure forge_tools are loaded
        try:
            from forge.execution.runtime import LocalRuntime
            from forge.models import Flow
            from forge_tools.populated_registry import registry as forge_registry

            # Register test tools into the forge registry with explicit schemas
            from flow.test_tools import TEST_TOOLS_REGISTRY

            # dummy_search_task schema
            forge_registry.register(
                TEST_TOOLS_REGISTRY["dummy_search_task"],
                function_id="dummy_search_task",
                input_schema={
                    "file_ids": "list",
                    "questions": "list",
                },
                output_schema={"search_results": "list"},
            )

            # dummy_answer_task schema
            forge_registry.register(
                TEST_TOOLS_REGISTRY["dummy_answer_task"],
                function_id="dummy_answer_task",
                input_schema={
                    "questions": "list",
                    "search_results": "list",
                },
                output_schema={"answers": "list"},
            )
            _logger.info("Using registry with %d tools", len(forge_registry._functions))
        except ImportError as e:
            _logger.error("Failed to import forge components: %s", e)
            _logger.error("Make sure forge and forge_tools are installed")
            return CustomWorkflowOutput(
                answers=[],
                collectionId=task_config.collectionId if task_config.collectionId else "",
            )

        # Convert flow dict to Flow object (Pydantic model)
        flow = Flow(**flow_dict)

        runtime = LocalRuntime(registry=forge_registry)
        try:
            # TODO: Update to pass elise_api_headers once forge supports it
            result = await runtime.run(
                flow=flow,
                inputs=flow_inputs,
                access_token=None,  # Old auth system - not used with new headers
                run_id=f"custom-workflow-{ctx.id}",
            )
        except Exception as e:
            _logger.error("Forge flow execution failed: %s", e)
            return CustomWorkflowOutput(
                answers=[],
                collectionId=task_config.collectionId if task_config.collectionId else "",
            )
        finally:
            await runtime.cleanup()

        _logger.info(
            "Forge flow %s completed with status %s",
            flow.flow_id,
            result.status,
        )

        if result.status != "succeeded":
            _logger.error("Forge flow failed: %s", result.error)
            return CustomWorkflowOutput(
                answers=[],
                collectionId=task_config.collectionId if task_config.collectionId else "",
            )

        # 5) Map outputs to QuestionAnswer list
        answers = OutputMapper.to_question_answers(
            flow_outputs=result.outputs,
            original_questions=list[Question](task_config.questions),
        )

        return CustomWorkflowOutput(
            answers=answers,
            collectionId=task_config.collectionId if task_config.collectionId else "",
        )

    def _resolve_flow_and_params(
        self,
        cfg: CustomWorkflowConfig,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Determine which Flow to use and extract additional params.

        Priority:
        1. Inline flow in additional_inputs (JSON with 'flow_id', 'steps', etc.)
        2. Named flow via workflow_id
        3. Default flow (qa_default)

        Returns:
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
