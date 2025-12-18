import datetime
import logging

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError, ApplicationError

with workflow.unsafe.imports_passed_through():
    from clark.temporal import kafka
    from clark.temporal.semconv import WorkflowSemConv

    from clark_protos.processors.api_pb2 import ProcessorMessageInput
    from clark_protos.processors.forge_pb2 import (
        ProcessorForgeConfig as ForgeConfig,
    )
    from clark_protos.processors.forge_pb2 import (
        ProcessorForgeOutput as ForgeOutput,
    )
    from clark_protos.processors.workflow_context_pb2 import WorkflowContext
    from flow.activity import ForgeActivity

_forge_semconv = WorkflowSemConv("ProcessorForge")

FORGE_WORKFLOW_TASK_QUEUE = _forge_semconv.task_queue()

_PROCESSOR_NAME = "processorForge"

_logger = workflow.LoggerAdapter(logging.getLogger(__name__), None)


@workflow.defn(name=_forge_semconv.type())
class TemporalForgeWorkflow:
    @workflow.run
    async def run(self, input_msg: ProcessorMessageInput) -> ForgeOutput:
        """Run the ProcessorForge workflow."""
        # Initialize task from Kafka
        task_config = await kafka.initialize_task_from_input(
            input_msg,
            output_cls=ForgeOutput,
            processor_name=_PROCESSOR_NAME,
            task_queue=FORGE_WORKFLOW_TASK_QUEUE,
            task_config_cls=ForgeConfig,
        )

        ctx = WorkflowContext(
            id=input_msg.jobConfig.jobId,
            elise_refresh_token=input_msg.headers["Refresh-Token"].decode("utf-8"),
        )

        _logger.info("Executing ForgeActivity.process")

        try:
            task_output = await workflow.execute_activity_method(
                ForgeActivity.process,
                args=[ctx, task_config],
                start_to_close_timeout=datetime.timedelta(minutes=30),
                task_queue=FORGE_WORKFLOW_TASK_QUEUE,
                retry_policy=RetryPolicy(maximum_attempts=1),
            )

        except ActivityError as exception:
            await kafka.send_task_failure_message(
                input_msg=input_msg,
                output_cls=ForgeOutput,
                processor_name=_PROCESSOR_NAME,
                task_queue=FORGE_WORKFLOW_TASK_QUEUE,
                exception=exception,
            )

            error_msg = (
                f"Failed to execute ProcessorForge with job ID "
                f"'{input_msg.jobConfig.jobId}'. Cause: {exception}"
            )
            raise ApplicationError(error_msg, type="ProcessorForgeError") from exception

        # Send output
        _logger.info("Sending ProcessorForge output")
        await kafka.send_task_output(
            task_output,
            input_msg=input_msg,
            processor_name=_PROCESSOR_NAME,
            task_queue=FORGE_WORKFLOW_TASK_QUEUE,
        )

        return task_output
