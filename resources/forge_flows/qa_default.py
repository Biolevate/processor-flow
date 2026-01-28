"""QA Default Flow - Python version.

This flow is automatically detected and loaded by FlowLoader.
Convention: must define a build_flow() function that returns a Flow object.
"""

from forge import Flow, FlowInputs, ReferenceCondition, Step, Task


def build_flow() -> Flow:
    """Build the default QA flow for CustomWorkflow processor.
    
    This flow orchestrates the QA pipeline:
    1. Check if files fit in context (fits_in_single_call_flow)
    2. Route to appropriate QA strategy:
       - Small files → qa_agent_flow_with_full_content (direct answer)
       - Large files → qa_agent_flow (with search)
    
    Uses CustomWorkflow standard inputs:
    - first_source_file_ids: list[str] (main documents to analyze)
    - second_source_file_ids: list[str] (reference documents, optional)
    - query: str (the question to answer)
    - previous_answers: list (for question chaining)
    
    All subflows are registered in forge_tools.populated_registry.
    """
    return Flow(
        version="1.0",
        flow_id="qa_default",
        name="Processor QA Default Flow",
        inputs=FlowInputs(
            parameters={
                "first_source_file_ids": "list",
                "second_source_file_ids": "list",
                "query": "str",
                "previous_answers": "list",
            },
            defaults={
                "second_source_file_ids": [],
                "previous_answers": [],
            },
        ),
        steps=[
            # Step 1: Check context size (use first source files)
            Step(
                step_id="fits_in_context",
                tasks=[
                    Task(
                        task_id="fits_in_context",
                        function="fits_in_single_call_flow",
                        inputs={"file_ids": "$flow.first_source_file_ids"},
                        export_to_flow=False,
                    ),
                ],
            ),
            # Step 2: QA with search (large files)
            Step(
                step_id="qa_agent",
                tasks=[
                    Task(
                        task_id="qa_agent",
                        function="qa_agent_flow",
                        inputs={
                            "file_ids": "$flow.first_source_file_ids",
                            "query": "$flow.query",
                            "previous_answers": "$flow.previous_answers",
                        },
                        export_to_flow=True,
                        when=ReferenceCondition(
                            ref="$fits_in_context.fits_in_context",
                            op="==",
                            value=False,
                        ),
                    ),
                ],
            ),
            # Step 3: QA with full content (small files)
            Step(
                step_id="qa_agent_with_full_content",
                tasks=[
                    Task(
                        task_id="qa_agent_with_full_content",
                        function="qa_agent_flow_with_full_content",
                        inputs={
                            "file_ids": "$flow.first_source_file_ids",
                            "query": "$flow.query",
                            "previous_answers": "$flow.previous_answers",
                        },
                        export_to_flow=True,
                    ),
                ],
                when=ReferenceCondition(
                    ref="$fits_in_context.fits_in_context",
                    op="==",
                    value=True,
                ),
            ),
        ],
    )

