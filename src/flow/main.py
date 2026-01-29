import asyncio
import logging
import os
import sys

from clark.temporal.worker import TemporalWorkerConfig
from dotenv import load_dotenv
from elise_client.api_client import ApiClient
from elise_client.configuration import Configuration
from pybl_healthcheck import HealthCheck

# Import protobuf modules to register them in the symbol database
# Legacy forge proto (kept for reference)
# from clark_protos.processors import forge_pb2
from clark_protos.processors import customWorkflow_pb2  # noqa: F401
from flow.activity import CustomWorkflowActivity
from flow.workflow import (
    CUSTOM_WORKFLOW_TASK_QUEUE,
    TemporalCustomWorkflowWorkflow,
)

_logger = logging.getLogger(__name__)

_GRACE_SEC = 10


def setup_logger() -> None:
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        stream=sys.stdout,
        force=True,
    )
    logging.getLogger("__main__").setLevel(logging.INFO)
    logging.getLogger("clark.temporal").setLevel(logging.INFO)
    logging.getLogger("forge").setLevel(logging.DEBUG)
    logging.getLogger("forge_tools").setLevel(logging.INFO)
    logging.getLogger("flow").setLevel(logging.INFO)
    logging.getLogger("temporalio.activity").setLevel(logging.INFO)


async def shutdown(*tasks: asyncio.Task[object], grace: float = _GRACE_SEC) -> None:
    _logger.warning("Shutdown requested, will wait for %s seconds", grace)
    for t in tasks:
        t.cancel()
    async with asyncio.timeout(grace):
        await asyncio.gather(*tasks, return_exceptions=True)


async def main() -> None:
    setup_logger()
    _logger.info("Starting ProcessorCustomWorkflow Worker")

    load_dotenv()

    healthcheck = HealthCheck()
    health_task = asyncio.create_task(healthcheck.start_http_server())

    # Important: import forge_tools.populated_registry to register all tools
    try:
        import forge_tools.populated_registry  # noqa: F401

        _logger.info("Successfully loaded forge_tools.populated_registry")
    except ImportError as e:
        _logger.error("Failed to import forge_tools.populated_registry: %s", e)
        _logger.error("Make sure forge_tools is installed")
        raise

    async with ApiClient(
        configuration=Configuration(
            host=os.getenv("ELISE_SERVER_URL", "http://localhost:8080"),
        ),
    ) as elise_api_client:
        custom_workflow_activity = CustomWorkflowActivity()

        # Worker 1: CustomWorkflow task queue (main processor workflows)
        custom_workflow_worker = await (
            TemporalWorkerConfig.from_env()
            .with_task_queue(CUSTOM_WORKFLOW_TASK_QUEUE)
            .with_workflows(TemporalCustomWorkflowWorkflow)
            .with_activities(custom_workflow_activity.process)
            .into_worker()
        )

        # Worker 2: forge-default task queue (for subflow activities)
        # Import forge activities and workflows for subflow execution
        from forge.adapters.temporal.activities import generate_activities
        from forge.adapters.temporal.workflows import ForgeWorkflow, OrchestratorWorkflow
        from forge_tools.populated_registry import registry as forge_registry
        from temporalio.worker import FixedSizeSlotSupplier, WorkerTuner

        # Create high-capacity tuner for forge worker (handles much more load)
        forge_tuner = WorkerTuner.create_composite(
            workflow_supplier=FixedSizeSlotSupplier(1000),
            activity_supplier=FixedSizeSlotSupplier(1000),
            local_activity_supplier=FixedSizeSlotSupplier(num_slots=1000),
            nexus_supplier=FixedSizeSlotSupplier(num_slots=100),
        )

        forge_activities = generate_activities(forge_registry)
        forge_worker = await (
            TemporalWorkerConfig.from_env()
            .with_task_queue("forge-default")
            .with_tuner(forge_tuner)
            .with_workflows(ForgeWorkflow, OrchestratorWorkflow)
            .with_activities(*forge_activities)
            .into_worker()
        )

        _logger.info("Running worker on CUSTOM_WORKFLOW_TASK_QUEUE and forge-default")
        worker_task_1 = asyncio.create_task(custom_workflow_worker.run())
        worker_task_2 = asyncio.create_task(forge_worker.run())

        try:
            await asyncio.gather(worker_task_1, worker_task_2)
        except asyncio.CancelledError:
            await shutdown(worker_task_1, worker_task_2, health_task, grace=_GRACE_SEC)

        _logger.info("Shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())
