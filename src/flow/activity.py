import logging

from clark.temporal.token_manager import TokenManager
from temporalio import activity

from clark_protos.processors.forge_pb2 import (
    ProcessorForgeConfig as ForgeConfig,
)
from clark_protos.processors.forge_pb2 import (
    ProcessorForgeOutput as ForgeOutput,
)
from clark_protos.processors.questionAnswering_pb2 import Question
from clark_protos.processors.workflow_context_pb2 import WorkflowContext
from flow.flow_loader import FlowLoader
from flow.io_mapping import InputMapper, OutputMapper

_logger = activity.LoggerAdapter(logging.getLogger(__name__), None)


class ForgeActivity:
    """Temporal activity that runs Forge flows for QA-like processing."""

    _token_manager: TokenManager
    _flow_loader: FlowLoader

    def __init__(self, token_manager: TokenManager) -> None:
        self._token_manager = token_manager
        self._flow_loader = FlowLoader()

    @activity.defn
    async def process(
        self,
        ctx: WorkflowContext,
        task_config: ForgeConfig,
    ) -> ForgeOutput:
        """Main activity entry - runs a Forge flow.

        Supports:
          - task_config.flow_json (inline flow)
          - task_config.flow_name (flow resource)
          - fallback to default 'qa_default' flow
        """
        _logger.info(
            "ForgeActivity.process(job_id=%s) with %d files and %d questions",
            ctx.id,
            len(task_config.files),
            len(task_config.questions),
        )

        # 1) Resolve flow
        flow_dict = self._resolve_flow(task_config)

        # 2) Build flow inputs
        flow_inputs = InputMapper.build_flow_inputs(
            files=list(task_config.files),
            questions=list(task_config.questions),
            extra_params=dict(task_config.flow_params) if hasattr(task_config, "flow_params") else None,
        )

        # 3) Acquire access token to be used by Forge tools
        # For local testing, skip token exchange if using dummy refresh token
        if ctx.elise_refresh_token == "dummy-refresh-token-for-local-testing":
            access_token = "dummy-access-token-for-local-testing"
            _logger.info("Using dummy access token for local testing")
        else:
            access_token = await self._token_manager.get_access_token(
                ctx.elise_refresh_token,
            )

        # 4) Execute flow with LocalRuntime
        # Import here to avoid circular dependencies and ensure forge_tools are loaded
        try:
            from forge.models import Flow
            from forge.runtime import LocalRuntime
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
            return ForgeOutput(answers=[])

        # Convert flow dict to Flow object (Pydantic model)
        flow = Flow(**flow_dict)

        runtime = LocalRuntime(registry=forge_registry)
        try:
            result = await runtime.run(
                flow=flow,
                inputs=flow_inputs,
                access_token=access_token,
                run_id=f"forge-{ctx.id}",
            )
        except Exception as e:
            _logger.error("Forge flow execution failed: %s", e)
            return ForgeOutput(answers=[])
        finally:
            await runtime.cleanup()

        _logger.info(
            "Forge flow %s completed with status %s",
            flow.flow_id,
            result.status,
        )

        if result.status != "succeeded":
            _logger.error("Forge flow failed: %s", result.error)
            return ForgeOutput(answers=[])

        # 5) Map outputs to QuestionAnswer list
        answers = OutputMapper.to_question_answers(
            flow_outputs=result.outputs,
            original_questions=list[Question](task_config.questions),
        )

        return ForgeOutput(answers=answers)

    def _resolve_flow(self, cfg: ForgeConfig):
        """Determine which Flow to use (inline JSON, named, or default)."""
        # Highest precedence: inline JSON
        if getattr(cfg, "flow_json", ""):
            _logger.info("Using inline Forge flow from config.flow_json")
            return self._flow_loader.load_from_json(cfg.flow_json)

        # Next: named flow
        if getattr(cfg, "flow_name", ""):
            _logger.info("Loading Forge flow by name: %s", cfg.flow_name)
            return self._flow_loader.load_by_name(cfg.flow_name)

        # Default
        default_name = "qa_default"
        _logger.info("No flow specified; using default flow '%s'", default_name)
        return self._flow_loader.load_by_name(default_name)
