"""Input/output mapping for Forge flows."""

import logging
from collections.abc import Sequence
from typing import Any

from clark_protos.models.file_pb2 import FileMetaData
from clark_protos.processors.questionAnswering_pb2 import (
    Question,
    QuestionAnswer,
)

logger = logging.getLogger(__name__)


def get_question_index(question: str, questions: Sequence[Question]) -> int:
    return next((i for i, q in enumerate(questions) if q.question == question), -1)


class InputMapper:
    """Map processor inputs to Forge flow inputs."""

    @staticmethod
    def files_to_dicts(files: list[FileMetaData]) -> list[dict[str, Any]]:
        return [
            {
                "id": f.id,
                "name": f.name,
                "checksum": f.checksum,
                "path": getattr(f, "path", ""),
                "extension": getattr(f, "extension", ""),
                "providerId": getattr(f, "providerId", ""),
            }
            for f in files
        ]

    @staticmethod
    def questions_to_dicts(questions: list[Question]) -> list[dict[str, Any]]:
        qs: list[dict[str, Any]] = []
        for q in questions:
            qs.append(
                {
                    "id": q.id,
                    "question": q.question,
                    "answerType": q.answerType,
                    "guidelines": q.guidelines,
                    "expectedAnswer": q.expectedAnswer,
                    "inputQuestionIds": list(q.inputQuestionIds),
                },
            )
        return qs

    @staticmethod
    def build_flow_inputs(
        files: list[FileMetaData],
        questions: list[Question],
        extra_params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Build canonical flow inputs for qa_default flow.
        
        For qa_default flow:
          - file_ids: list[str]
          - query: str (first question)
          - previous_answers: list (from question dependencies)
        
        For other flows (test_simple, etc.):
          - file_ids: list[str]
          - files: list[dict]
          - questions: list[dict]
        """
        file_ids = [f.id for f in files]

        # For qa_default flow: single query mode
        query = questions[0].question if questions else ""

        # Build previous_answers from dependencies if needed
        previous_answers = []
        if questions and questions[0].inputQuestionIds:
            # TODO: Retrieve answers from dependent questions
            # For now, leave empty
            pass

        inputs: dict[str, Any] = {
            "file_ids": file_ids,
            "query": query,
            "previous_answers": previous_answers,
            # Keep legacy format for backwards compatibility
            "files": InputMapper.files_to_dicts(files),
            "questions": InputMapper.questions_to_dicts(questions),
        }

        if extra_params:
            inputs["extra_params"] = dict(extra_params)

        return inputs

    @staticmethod
    def build_custom_workflow_inputs(
        first_source_files: list[FileMetaData],
        second_source_files: list[FileMetaData],
        questions: list[Question],
        additional_params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build flow inputs with custom workflow convention.
        
        Standard CustomWorkflow inputs:
        - first_source_file_ids: list[str]
        - second_source_file_ids: list[str]
        - query: str (first question)
        - questions: list[dict]
        - previous_answers: list
        - **additional_params: from additional_inputs JSON
        
        Flows MUST use these standard input names.
        """
        inputs: dict[str, Any] = {
            "first_source_file_ids": [f.id for f in first_source_files],
            "second_source_file_ids": [f.id for f in second_source_files],
            "query": questions[0].question if questions else "",
            "questions": InputMapper.questions_to_dicts(questions),
            "previous_answers": [],
        }

        # Merge additional params from additional_inputs
        if additional_params:
            logger.info("Merging additional params into flow inputs: %s", additional_params)
            inputs.update(additional_params)

        return inputs


class OutputMapper:
    """Map Forge flow outputs to QuestionAnswer protos."""

    @staticmethod
    def to_question_answers(
        flow_outputs: dict[str, Any],
        original_questions: list[Question],
    ) -> list[QuestionAnswer]:
        """Convert flow outputs → QuestionAnswer list.
        
        Supports multiple output formats:
        1. qa_default flow (outputs from looping_agent with final_result)
        2. Legacy answers format
        """
        # Case 1: qa_default flow output (looping_agent returns final_result directly)
        if "final_result" in flow_outputs:
            return OutputMapper._handle_qa_default(flow_outputs, original_questions)

        # Case 2: Legacy format
        return OutputMapper._handle_legacy_format(flow_outputs, original_questions)

    @staticmethod
    def _handle_qa_default(
        flow_outputs: dict[str, Any],
        original_questions: list[Question],
    ) -> list[QuestionAnswer]:
        """Handle output from qa_default flow (single question).
        
        The looping_agent returns outputs merged directly into flow_outputs:
        - finished: bool
        - iterations: int
        - final_result: dict
        - conversation: list
        """
        # Extract final_result from looping_agent output
        final_result = flow_outputs.get("final_result", {})
        if not final_result:
            logger.warning("No final_result found in flow outputs")
            return []

        # Create QuestionAnswer for the first question
        q = original_questions[0] if original_questions else None
        if not q:
            logger.warning("No original questions provided")
            return []

        # Extract content IDs and join them
        justifying_ids = final_result.get("justifying_contents_ids", [])
        sourced_content = ", ".join(justifying_ids) if justifying_ids else ""

        qa = QuestionAnswer(
            id=q.id,
            question=q.question,
            expectedAnswer=final_result.get("answer", ""),
            sourcedContent=sourced_content,
            explanation=final_result.get("answer_explanation", ""),
            answerValidity=1.0,  # TODO: calculate from quality metrics
            validityExplanation="",
        )

        # Add dependencies
        for dep in q.inputQuestionIds:
            qa.inputQuestionIds.append(dep)

        return [qa]

    @staticmethod
    def _handle_legacy_format(
        flow_outputs: dict[str, Any],
        original_questions: list[Question],
    ) -> list[QuestionAnswer]:
        """Handle legacy answers format."""
        raw_answers = flow_outputs.get("answers") or []
        answers: list[QuestionAnswer] = []

        for raw in raw_answers:
            qa = QuestionAnswer(
                id=str(raw.get("id", "")),
                question=str(raw.get("question", "")),
                expectedAnswer=str(raw.get("expectedAnswer", "")),
                sourcedContent=str(
                    raw.get("sourcedContent", raw.get("answer", "")),
                ),
                explanation=str(
                    raw.get(
                        "explanation",
                        raw.get("answerExplanation", raw.get("rationale", "")),
                    ),
                ),
                answerValidity=float(raw.get("answerValidity", 0.0)),
                validityExplanation=str(
                    raw.get("validityExplanation", ""),
                ),
            )

            # Optional: annotations as list[dict]
            for ann in raw.get("annotations") or []:
                try:
                    qa.annotations.add(**ann)
                except TypeError:
                    logger.debug("Skipping incompatible annotation: %r", ann)

            # Optional: dependency IDs
            for dep in raw.get("inputQuestionIds") or []:
                qa.inputQuestionIds.append(dep)

            answers.append(qa)

        # Preserve original ordering where possible
        answers.sort(
            key=lambda a: get_question_index(a.question, original_questions),
        )

        return answers

