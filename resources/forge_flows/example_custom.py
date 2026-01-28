"""Example custom flow - demonstrates Python flow creation.

This is a template for creating your own Python flows.
Simply copy this file, rename it, and modify the build_flow() function.
"""

from forge import Flow, FlowInputs, ReferenceCondition, Step, Task


def build_flow() -> Flow:
    """Build a custom example flow.
    
    This flow demonstrates:
    - Multiple steps
    - Conditional execution
    - Task dependencies
    - Parameter passing

    To use this flow:
        config = ProcessorForgeConfig(
            files=files,
            questions=questions,
            flow_name="example_custom",  # Matches filename
        )
    """
    return Flow(
        version="1.0",
        flow_id="example_custom",
        name="Example Custom Flow",
        inputs=FlowInputs(
            parameters={
                "file_ids": "list",
                "query": "str",
                "threshold": "int",
            },
            defaults={
                "threshold": 10,
            },
        ),
        steps=[
            # Step 1: Initial processing
            Step(
                step_id="preprocess",
                tasks=[
                    Task(
                        task_id="analyze_files",
                        function="dummy_search_task",  # Replace with real function
                        inputs={
                            "file_ids": "$flow.file_ids",
                            "questions": [{"question": "$flow.query"}],
                        },
                        export_to_flow=False,
                    ),
                ],
            ),

            # Step 2: Conditional path A (threshold met)
            Step(
                step_id="path_a",
                tasks=[
                    Task(
                        task_id="handle_path_a",
                        function="dummy_answer_task",  # Replace with real function
                        inputs={
                            "questions": [{"question": "$flow.query"}],
                            "search_results": "$analyze_files.search_results",
                        },
                        export_to_flow=True,
                    ),
                ],
                when=ReferenceCondition(
                    ref="$flow.threshold",
                    op=">=",
                    value=10,
                ),
            ),

            # Step 3: Conditional path B (threshold not met)
            Step(
                step_id="path_b",
                tasks=[
                    Task(
                        task_id="handle_path_b",
                        function="dummy_answer_task",  # Replace with real function
                        inputs={
                            "questions": [{"question": "$flow.query"}],
                            "search_results": [],
                        },
                        export_to_flow=True,
                    ),
                ],
                when=ReferenceCondition(
                    ref="$flow.threshold",
                    op="<",
                    value=10,
                ),
            ),
        ],
    )


# Optional: Add helper functions for complex flows
def get_default_threshold() -> int:
    """Get default threshold value."""
    return 10

