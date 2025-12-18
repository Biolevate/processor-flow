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
    try:
        api_client = ApiClient()
        api_client.configuration.host = SERVER_ADDRESS
        api = AuthControllerApi(api_client)
        response = await api.login(
            login_request=LoginRequest(username=API_USERNAME, password=API_PASSWORD),
        )
        return response.refresh_token or ""
    except Exception as e:
        logger.warning("Failed to fetch refresh token: %s. Using dummy token for testing.", e)
        return "dummy-refresh-token-for-local-testing"


doc_checksums = [
    "353c0ff54d2856fbe3cd458565fc0705",
    "3ffe9425a210a4ecccb3f4f846bfc091",
    "855de953eaefa1ccbc7297ae52d65e89",
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
    Question(
        id="q2",
        question="List all authors mentioned in the document",
        answerType=ExpectedAnswerType(
            type=DataType.STRING,
            multivalued=True,
        ),
        guidelines="Extract full author names",
        expectedAnswer="",
    ),
    Question(
        id="q3",
        question="What are the key findings?",
        answerType=ExpectedAnswerType(
            type=DataType.STRING,
            multivalued=False,
        ),
        guidelines="Summarize the main findings or conclusions",
        expectedAnswer="",
        inputQuestionIds=["q1"],  # Depends on q1
    ),
]

files = [
    FileMetaData(
        id=f"file-{i}",
        name="",
        path="",
        checksum=checksum,
        extension="pdf",
        providerId="29ba7d68-a11d-4c77-8201-b4e51d5039a1",
    )
    for i, checksum in enumerate(doc_checksums)
]


@dataclass
class ForgeRun:
    config: ProcessorForgeConfig

    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    async def run(self, client: TemporalClient) -> None:
        logger.info("Running Flow test %s", self.id)

        processor_config = any_pb2.Any()
        processor_config.Pack(self.config)

        # Fetch refresh token
        refresh_token = await fetch_refresh_token()

        processor_message_input = ProcessorMessageInput(
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
    # Test with simple test flow (uses dummy tasks)
    ForgeRun(
        config=ProcessorForgeConfig(
            files=files[:1],
            questions=questions[:2],  # Test without dependency
            flow_name="test_simple",
        ),
    ),
    # Test with dependency handling
    ForgeRun(
        config=ProcessorForgeConfig(
            files=files[:1],
            questions=questions,  # Test with dependency (q3 depends on q1)
            flow_name="test_simple",
        ),
    ),
    # Test with multiple files
    ForgeRun(
        config=ProcessorForgeConfig(
            files=files,
            questions=questions,
            flow_name="test_simple",
        ),
    ),
]


async def main() -> None:
    setup_logger()

    # Start worker
    worker_task = asyncio.create_task(worker_main())

    # Give worker time to start
    await asyncio.sleep(2)

    logger.info("Running Flow Temporal Workflows...")

    # Run workflow concurrently
    client = await TemporalClientConfig.from_env().into_client()
    await asyncio.gather(*(run.run(client) for run in runs))

    logger.info("Finished running workflows, shutting down...")

    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass


if __name__ == "__main__":
    asyncio.run(main())
