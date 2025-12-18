import asyncio
import logging
import os
import sys

from clark.temporal.token_manager import TokenManager
from clark.temporal.worker import TemporalWorkerConfig
from dotenv import load_dotenv
from japtp_rs import AsyncEasTokenExchangeClient
from pybl_healthcheck import HealthCheck

from flow.activity import ForgeActivity
from flow.workflow import (
    FORGE_WORKFLOW_TASK_QUEUE,
    TemporalForgeWorkflow,
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


async def shutdown(*tasks: asyncio.Task[object], grace: float = _GRACE_SEC) -> None:
    _logger.warning("Shutdown requested, will wait for %s seconds", grace)
    for t in tasks:
        t.cancel()
    async with asyncio.timeout(grace):
        await asyncio.gather(*tasks, return_exceptions=True)


async def main() -> None:
    setup_logger()
    _logger.info("Starting ProcessorForge Worker")

    load_dotenv()

    healthcheck = HealthCheck()
    health_task = asyncio.create_task(healthcheck.start_http_server())

    # JAPTP EAS token exchange client (JA -> IAT)
    eas_client = AsyncEasTokenExchangeClient(
        base_url=os.getenv("EXCHANGE_URL", ""),
        client_id=os.getenv("EXCHANGE_CLIENT_ID", ""),
        client_secret=os.getenv("EXCHANGE_CLIENT_SECRET", ""),
    )

    token_manager = TokenManager.new_iat(eas_client)

    # Important: import forge_tools.populated_registry to register all tools
    try:
        import forge_tools.populated_registry  # noqa: F401
        _logger.info("Successfully loaded forge_tools.populated_registry")
    except ImportError as e:
        _logger.error("Failed to import forge_tools.populated_registry: %s", e)
        _logger.error("Make sure forge_tools is installed")
        raise

    forge_activity = ForgeActivity(token_manager=token_manager)

    worker = await (
        TemporalWorkerConfig.from_env()
        .with_task_queue(FORGE_WORKFLOW_TASK_QUEUE)
        .with_workflows(TemporalForgeWorkflow)
        .with_activities(forge_activity.process)
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
