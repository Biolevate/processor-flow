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
        """Build canonical flow inputs.

        Default convention for QA-like flows:
          - file_ids: list[str]
          - files: list[dict]
          - questions: list[dict]
          - extra_params: dict[str, str]
        """
        file_ids = [f.id for f in files]
        inputs: dict[str, Any] = {
            "file_ids": file_ids,
            "files": InputMapper.files_to_dicts(files),
            "questions": InputMapper.questions_to_dicts(questions),
        }
        if extra_params:
            inputs["extra_params"] = dict(extra_params)
        return inputs


class OutputMapper:
    """Map Forge flow outputs to QuestionAnswer protos."""

    @staticmethod
    def to_question_answers(
        flow_outputs: dict[str, Any],
        original_questions: list[Question],
    ) -> list[QuestionAnswer]:
        """Convert flow outputs → QuestionAnswer list.

        Contract for QA-like flows:
          flow.outputs["answers"] is a list of dicts:
            {
              "id": ...,
              "question": ...,
              "expectedAnswer": ...,
              "sourcedContent": ...,
              "explanation": ...,
              "answerValidity": float,
              "validityExplanation": str,
              "annotations": [...],
              "inputQuestionIds": [...],
            }
        """
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
                    # If ann is already a proto dict, this may work; else adapt as needed
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

