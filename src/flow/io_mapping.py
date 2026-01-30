"""Input/output mapping for Forge flows."""

import logging
from collections.abc import Sequence
from typing import Any

from google.protobuf.json_format import MessageToDict

from clark_protos.models.annotation_pb2 import (
    Annotation,
    AnnotationType,
    DocumentStatement,
)
from clark_protos.models.file_pb2 import FileMetaData
from clark_protos.models.position_pb2 import Bbox, Position, PositionBbox
from clark_protos.processors.questionAnswering_pb2 import (
    Question,
    QuestionAnswer,
)

logger = logging.getLogger(__name__)


def get_question_index(question: str, questions: Sequence[Question]) -> int:
    """Find the index of a question in a list by question text.

    Returns -1 if not found.
    """
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
            # Convert protobuf messages to dicts for JSON serialization
            answer_type_dict = MessageToDict(q.answerType, preserving_proto_field_name=True) if q.HasField("answerType") else {}
            expected_answer = q.expectedAnswer if isinstance(q.expectedAnswer, str) else ""

            qs.append(
                {
                    "id": q.id,
                    "question": q.question,
                    "answerType": answer_type_dict,
                    "guidelines": q.guidelines,
                    "expectedAnswer": expected_answer,
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
    """Map Forge flow outputs to QuestionAnswer protos.
    
    STANDARD OUTPUT FORMAT:
    Flows MUST return outputs with one of these structures:
    
    1. Single-question format (qa_default):
       {
           "final_result": {
               "answer": str,
               "justifying_contents_ids": list[str],
               "answer_explanation": str
           },
           "finished": bool,
           "iterations": int,
           ...
       }
    
    2. Multi-question format:
       {
           "answers": [
               {
                   "id": str,
                   "question": str,
                   "answer": str,
                   "justifying_contents_ids": list[str],
                   "answer_explanation": str,
                   "answer_validity": float (0.0-1.0),
                   "validity_explanation": str (optional),
                   "input_question_ids": list[str] (optional)
               },
               ...
           ]
       }
    
    Any other format will be rejected.
    """

    @staticmethod
    def to_question_answers(
        flow_outputs: dict[str, Any],
        original_questions: list[Question],
    ) -> list[QuestionAnswer]:
        """Convert flow outputs → QuestionAnswer list.
        
        Enforces strict output format compliance.
        """
        # Case 1: Single-question format (qa_default flow)
        if "final_result" in flow_outputs:
            return OutputMapper._handle_single_question(flow_outputs, original_questions)

        # Case 2: Multi-question format
        if "answers" in flow_outputs:
            return OutputMapper._handle_multi_question(flow_outputs, original_questions)

        # No valid format found
        error_msg = (
            "Flow output does not match required format. "
            "Expected either 'final_result' (single-question) or 'answers' (multi-question). "
            f"Got keys: {list(flow_outputs.keys())}"
        )
        logger.error(error_msg)
        raise ValueError(error_msg)

    @staticmethod
    def _handle_single_question(
        flow_outputs: dict[str, Any],
        original_questions: list[Question],
    ) -> list[QuestionAnswer]:
        """Handle single-question output format (qa_default flow).
        
        REQUIRED format:
        {
            "final_result": {
                "answer": str,
                "justifying_contents_ids": list[str],
                "answer_explanation": str,
                "annotations": list[dict] (optional - full annotation objects)
            },
            ...
        }
        
        OUTPUT FORMAT (matching processor_questionAnswering):
        - sourcedContent: "[answer text](cite:id1,id2,...)"
        - expectedAnswer: original expected answer from question input (empty if not provided)
        - annotations: list of Annotation protos with documentStatement
        """
        final_result = flow_outputs.get("final_result")
        if not final_result or not isinstance(final_result, dict):
            error_msg = "Missing or invalid 'final_result' in flow outputs"
            logger.error(error_msg)
            raise ValueError(error_msg)

        # Validate required fields
        required_fields = {"answer", "justifying_contents_ids", "answer_explanation"}
        missing_fields = required_fields - set(final_result.keys())
        if missing_fields:
            error_msg = f"Missing required fields in final_result: {missing_fields}"
            logger.error(error_msg)
            raise ValueError(error_msg)

        # Validate types
        if not isinstance(final_result["answer"], str):
            msg = "final_result.answer must be a string"
            raise TypeError(msg)
        if not isinstance(final_result["justifying_contents_ids"], list):
            msg = "final_result.justifying_contents_ids must be a list"
            raise TypeError(msg)
        if not isinstance(final_result["answer_explanation"], str):
            msg = "final_result.answer_explanation must be a string"
            raise TypeError(msg)

        # Get the original question
        if not original_questions:
            error_msg = "No original questions provided for single-question output"
            logger.error(error_msg)
            raise ValueError(error_msg)

        q = original_questions[0]

        # Build sourcedContent with citation marks: [answer](cite:id1,id2,...)
        answer_text = final_result["answer"]
        citation_ids = list(final_result.get("citation_annotation_ids", []) or [])
        if final_result["justifying_contents_ids"] and not citation_ids:
            msg = (
                "final_result.justifying_contents_ids is non-empty but citation_annotation_ids is missing. "
                "Annotation enrichment is required for QuestionAnswering-compatible output."
            )
            raise ValueError(msg)
        if citation_ids:
            cite_refs = ",".join(citation_ids)
            sourced_content = f"[{answer_text}](cite:{cite_refs})"
        else:
            sourced_content = answer_text

        # Build annotations from flow output if available
        annotations = OutputMapper._build_annotations(final_result.get("annotations", []))

        qa = QuestionAnswer(
            id=q.id,
            question=q.question,
            expectedAnswer=q.expectedAnswer,  # Original expected answer from input
            sourcedContent=sourced_content,
            explanation=final_result["answer_explanation"],
            answerValidity=final_result.get("answer_validity", 1.0),
            validityExplanation=final_result.get("validity_explanation", ""),
        )

        # Add annotations
        for ann in annotations:
            qa.annotations.append(ann)

        # Add dependencies
        for dep in q.inputQuestionIds:
            qa.inputQuestionIds.append(dep)

        return [qa]

    @staticmethod
    def _handle_multi_question(
        flow_outputs: dict[str, Any],
        original_questions: list[Question],
    ) -> list[QuestionAnswer]:
        """Handle multi-question output format.
        
        REQUIRED format:
        {
            "answers": [
                {
                    "id": str,
                    "question": str,
                    "answer": str,
                    "justifying_contents_ids": list[str],
                    "answer_explanation": str,
                    "answer_validity": float (optional, defaults to 1.0),
                    "validity_explanation": str (optional, defaults to ""),
                    "input_question_ids": list[str] (optional),
                    "expected_answer": str (optional - original expected answer),
                    "annotations": list[dict] (optional - full annotation objects)
                },
                ...
            ]
        }
        
        OUTPUT FORMAT (matching processor_questionAnswering):
        - sourcedContent: "[answer text](cite:id1,id2,...)"
        - expectedAnswer: original expected answer from question input
        - annotations: list of Annotation protos with documentStatement
        """
        raw_answers = flow_outputs.get("answers")
        if not isinstance(raw_answers, list):
            error_msg = "'answers' must be a list"
            logger.error(error_msg)
            raise TypeError(error_msg)

        # Build a lookup for original questions by ID
        questions_by_id = {q.id: q for q in original_questions}

        answers: list[QuestionAnswer] = []

        for idx, raw in enumerate(raw_answers):
            if not isinstance(raw, dict):
                error_msg = f"Answer at index {idx} must be a dict"
                logger.error(error_msg)
                raise TypeError(error_msg)

            # Validate required fields
            required_fields = {"id", "question", "answer", "justifying_contents_ids", "answer_explanation"}
            missing_fields = required_fields - set(raw.keys())
            if missing_fields:
                error_msg = f"Answer at index {idx} missing required fields: {missing_fields}"
                logger.error(error_msg)
                raise ValueError(error_msg)

            # Validate types
            if not isinstance(raw["id"], str):
                msg = f"Answer {idx}: 'id' must be a string"
                raise TypeError(msg)
            if not isinstance(raw["question"], str):
                msg = f"Answer {idx}: 'question' must be a string"
                raise TypeError(msg)
            if not isinstance(raw["answer"], str):
                msg = f"Answer {idx}: 'answer' must be a string"
                raise TypeError(msg)
            if not isinstance(raw["justifying_contents_ids"], list):
                msg = f"Answer {idx}: 'justifying_contents_ids' must be a list"
                raise TypeError(msg)
            if not isinstance(raw["answer_explanation"], str):
                msg = f"Answer {idx}: 'answer_explanation' must be a string"
                raise TypeError(msg)

            # Build sourcedContent with citation marks: [answer](cite:id1,id2,...)
            answer_text = raw["answer"]
            citation_ids = list(raw.get("citation_annotation_ids", []) or [])
            if raw["justifying_contents_ids"] and not citation_ids:
                msg = (
                    f"Answer {idx}: justifying_contents_ids is non-empty but citation_annotation_ids is missing. "
                    "Annotation enrichment is required for QuestionAnswering-compatible output."
                )
                raise ValueError(msg)
            if citation_ids:
                cite_refs = ",".join(citation_ids)
                sourced_content = f"[{answer_text}](cite:{cite_refs})"
            else:
                sourced_content = answer_text

            # Get original expected answer from the question input
            original_q = questions_by_id.get(raw["id"])
            expected_answer = raw.get("expected_answer", "")
            if not expected_answer and original_q:
                expected_answer = original_q.expectedAnswer

            # Build annotations from flow output if available
            annotations = OutputMapper._build_annotations(raw.get("annotations", []))

            # Create QuestionAnswer
            qa = QuestionAnswer(
                id=raw["id"],
                question=raw["question"],
                expectedAnswer=expected_answer,
                sourcedContent=sourced_content,
                explanation=raw["answer_explanation"],
                answerValidity=float(raw.get("answer_validity", 1.0)),
                validityExplanation=raw.get("validity_explanation", ""),
            )

            # Add annotations
            for ann in annotations:
                qa.annotations.append(ann)

            # Optional: dependency IDs
            for dep in raw.get("input_question_ids") or []:
                qa.inputQuestionIds.append(dep)

            answers.append(qa)

        # Preserve original ordering where possible
        answers.sort(
            key=lambda a: get_question_index(a.question, original_questions),
        )

        return answers

    @staticmethod
    def _build_annotations(raw_annotations: list[dict[str, Any]]) -> list[Annotation]:
        """Build Annotation protos from raw annotation dicts.
        
        Expected format for each annotation:
        {
            "id": str,
            "documentStatement": {
                "documentId": str,
                "documentName": str,
                "content": str,
                "positions": [
                    {
                        "bboxPosition": {
                            "bbox": {"x0": float, "y0": float, "x1": float, "y1": float},
                            "pageNumber": int (optional, defaults to 0)
                        }
                    },
                    ...
                ]
            }
        }
        """
        annotations: list[Annotation] = []

        for raw in raw_annotations:
            if not isinstance(raw, dict):
                logger.warning("Skipping non-dict annotation: %s", raw)
                continue

            ann_id = raw.get("id", "")
            doc_stmt_raw = raw.get("documentStatement", {})

            if not doc_stmt_raw:
                logger.warning("Skipping annotation without documentStatement: %s", ann_id)
                continue

            # Build positions
            positions: list[Position] = []
            for pos_raw in doc_stmt_raw.get("positions", []):
                bbox_pos_raw = pos_raw.get("bboxPosition", {})
                bbox_raw = bbox_pos_raw.get("bbox", {})

                if bbox_raw:
                    bbox = Bbox(
                        x0=float(bbox_raw.get("x0", 0)),
                        y0=float(bbox_raw.get("y0", 0)),
                        x1=float(bbox_raw.get("x1", 0)),
                        y1=float(bbox_raw.get("y1", 0)),
                    )
                    position_bbox = PositionBbox(
                        bbox=bbox,
                        page_number=int(bbox_pos_raw.get("pageNumber", 0)),
                    )
                    positions.append(Position(bboxPosition=position_bbox))

            # Build DocumentStatement
            doc_stmt = DocumentStatement(
                documentId=doc_stmt_raw.get("documentId", ""),
                documentName=doc_stmt_raw.get("documentName", ""),
                content=doc_stmt_raw.get("content", ""),
            )
            for pos in positions:
                doc_stmt.positions.append(pos)

            # Build Annotation
            annotation = Annotation(
                id=ann_id,
                type=AnnotationType.DOCUMENT_STATEMENT,
                documentStatement=doc_stmt,
            )
            annotations.append(annotation)

        return annotations

