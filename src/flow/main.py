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
# from clark_protos.processors import forge_pb2  # noqa: F401
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

        worker = await (
            TemporalWorkerConfig.from_env()
            .with_task_queue(CUSTOM_WORKFLOW_TASK_QUEUE)
            .with_workflows(TemporalCustomWorkflowWorkflow)
            .with_activities(custom_workflow_activity.process)
            .into_worker()
        )

        worker_task = asyncio.create_task(worker.run())

        try:
            await worker_task
        except asyncio.CancelledError:
            await shutdown(worker_task, health_task, grace=_GRACE_SEC)

        _logger.info("Shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())
