import asyncio
import logging
import os
import uuid
from dataclasses import dataclass, field

from clark.temporal.client import TemporalClientConfig
from dotenv import load_dotenv
from elise_client.api.auth_controller_api import AuthControllerApi
from elise_client.api_client import ApiClient
from elise_client.models.login_request import LoginRequest
from google.protobuf import any_pb2
from temporalio.client import Client as TemporalClient

from clark_protos.models.answer_pb2 import DataType, ExpectedAnswerType
from clark_protos.models.file_pb2 import FileMetaData
from clark_protos.processors.api_pb2 import ProcessorMessageInput
from clark_protos.processors.forge_pb2 import ProcessorForgeConfig
from clark_protos.processors.job_pb2 import JobCommand, JobConfiguration
from clark_protos.processors.questionAnswering_pb2 import Question
from flow.main import main as worker_main
from flow.main import setup_logger
from flow.workflow import FORGE_WORKFLOW_TASK_QUEUE, TemporalForgeWorkflow

load_dotenv()
logger = logging.getLogger(__name__)

# Server configuration for fetching refresh token
SERVER_ADDRESS = os.getenv("ELISE_SERVER_URL", "http://localhost:8080")
API_USERNAME = os.getenv("API_USERNAME", "sysadmin@biolevate.com")
API_PASSWORD = os.getenv("API_PASSWORD", "sysadmin")


async def fetch_refresh_token() -> str:
    """Fetch refresh token from biolevate server."""
    api_client = ApiClient()
    api_client.configuration.host = SERVER_ADDRESS
    try:
        api = AuthControllerApi(api_client)
        response = await api.login(
            login_request=LoginRequest(username=API_USERNAME, password=API_PASSWORD),
        )
        return response.refresh_token or ""
    finally:
        await api_client.close()


# Simple test configuration - using same file as processor-questionAnswering
test_file_id = "75de269e-a343-408d-b21a-ec297365a964"
test_checksum = "eca577d9913ffab69d0951ca8ace2de2"

files = [
    FileMetaData(
        id=test_file_id,
        checksum=test_checksum,
        name="test_document.pdf",
    ),
]

questions = [
    Question(
        id="q1",
        question="What is the main topic of this document?",
        answerType=ExpectedAnswerType(
            type=DataType.STRING,
            multivalued=False,
        ),
        guidelines="Provide a concise summary of the main topic",
        expectedAnswer="",
    ),
]


@dataclass
class ForgeRun:
    config: ProcessorForgeConfig

    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    async def run(self, client: TemporalClient) -> None:
        logger.info("Running Flow workflow %s", self.id)
        processor_config = any_pb2.Any()
        processor_config.Pack(self.config)

        # Fetch refresh token for biolevate server access
        refresh_token = await fetch_refresh_token()

        processor_message_input = ProcessorMessageInput(
            jobConfig=JobConfiguration(
                jobId=self.id,
                jobCommand=JobCommand.START,
            ),
            processorConfig=processor_config,
            headers=[("Refresh-Token", bytes(refresh_token, "utf-8"))],
        )

        result = await client.execute_workflow(
            TemporalForgeWorkflow.run,
            processor_message_input,
            id=self.id,
            task_queue=FORGE_WORKFLOW_TASK_QUEUE,
        )
        logger.info("Run %s output: %s", self.id, result)


runs = [
    # Test: qa_default flow with simple question on specific document
    ForgeRun(
        config=ProcessorForgeConfig(
            files=files,
            questions=questions,
            # flow_name not specified → uses qa_default.py automatically
        ),
    ),
]


async def main() -> None:
    # Start the worker in the background
    worker_task = asyncio.create_task(worker_main())
    logger.info("Running Flow Temporal Workflows...")

    client = await TemporalClientConfig.from_env().into_client()
    await asyncio.gather(*(run.run(client) for run in runs))

    logger.info("Finished running workflows, shutting down worker...")
    worker_task.cancel()
    await worker_task


if __name__ == "__main__":
    setup_logger()
    asyncio.run(main())
