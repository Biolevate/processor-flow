import datetime
import logging

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError, ApplicationError

with workflow.unsafe.imports_passed_through():
    from clark.temporal import kafka
    from clark.temporal.semconv import WorkflowSemConv

    from clark_protos.processors.api_pb2 import ProcessorMessageInput

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
    from clark_protos.processors.workflow_context_pb2 import WorkflowContext
    from flow.activity import CustomWorkflowActivity

_custom_workflow_semconv = WorkflowSemConv("CustomWorkflow")

CUSTOM_WORKFLOW_TASK_QUEUE = _custom_workflow_semconv.task_queue()

_PROCESSOR_NAME = "customWorkflow"

_logger = workflow.LoggerAdapter(logging.getLogger(__name__), None)


@workflow.defn(name=_custom_workflow_semconv.type())
class TemporalCustomWorkflowWorkflow:
    @workflow.run
    async def run(self, input_msg: ProcessorMessageInput) -> CustomWorkflowOutput:
        """Run the ProcessorCustomWorkflow workflow."""
        # Initialize task from Kafka
        task_config = await kafka.initialize_task_from_input(
            input_msg,
            output_cls=CustomWorkflowOutput,
            processor_name=_PROCESSOR_NAME,
            task_queue=CUSTOM_WORKFLOW_TASK_QUEUE,
            task_config_cls=CustomWorkflowConfig,
        )

        ctx = WorkflowContext(
            id=input_msg.jobConfig.jobId,
            headers={
                key: value.decode("utf-8")
                for key, value in input_msg.headers.items()
                if key in {"X-Biolevate-Principal", "X-Biolevate-Signature"}
            },
        )

        _logger.info("Executing CustomWorkflowActivity.process")

        try:
            task_output = await workflow.execute_activity_method(
                CustomWorkflowActivity.process,
                args=[ctx, task_config],
                start_to_close_timeout=datetime.timedelta(minutes=30),
                task_queue=CUSTOM_WORKFLOW_TASK_QUEUE,
                retry_policy=RetryPolicy(maximum_attempts=1),
            )

        except ActivityError as exception:
            await kafka.send_task_failure_message(
                input_msg=input_msg,
                output_cls=CustomWorkflowOutput,
                processor_name=_PROCESSOR_NAME,
                task_queue=CUSTOM_WORKFLOW_TASK_QUEUE,
                exception=exception,
            )

            error_msg = (
                f"Failed to execute ProcessorCustomWorkflow with job ID "
                f"'{input_msg.jobConfig.jobId}'. Cause: {exception}"
            )
            raise ApplicationError(error_msg, type="ProcessorCustomWorkflowError") from exception

        # Send output
        _logger.info("Sending ProcessorCustomWorkflow output")
        await kafka.send_task_output(
            task_output,
            input_msg=input_msg,
            processor_name=_PROCESSOR_NAME,
            task_queue=CUSTOM_WORKFLOW_TASK_QUEUE,
        )

        return task_output
