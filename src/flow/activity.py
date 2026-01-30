from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from forge.execution import ExecutionContext
from temporalio import activity

from clark_protos.processors.customWorkflow_pb2 import (
    ProcessorCustomWorkflowConfig as CustomWorkflowConfig,
)
from clark_protos.processors.customWorkflow_pb2 import (
    ProcessorCustomWorkflowOutput as CustomWorkflowOutput,
)
from clark_protos.processors.questionAnswering_pb2 import Question
from clark_protos.processors.workflow_context_pb2 import WorkflowContext
from flow.flow_loader import FlowLoader
from flow.io_mapping import InputMapper, OutputMapper

_logger = activity.LoggerAdapter(logging.getLogger(__name__), None)


async def _enrich_with_annotations(  # noqa: C901, PLR0912, PLR0915
    flow_outputs: dict[str, Any],
    source_files: list[Any],
) -> dict[str, Any]:
    """Enrich flow outputs with QuestionAnswering-style annotations.

    The `qa_default` flow returns `justifying_contents_ids` as **chunk IDs**.
    The `processor-questionAnswering` output expects:
    - `annotations[].id` to be a stable UUID derived from (file_uuid, chunk_id)
    - `sourcedContent` citations to reference these annotation IDs

    This function therefore:
    - fetches **all chunks per source document** using search client by **checksum**
    - builds annotations for the specific `justifying_contents_ids`
    - adds `annotations` and `citation_annotation_ids` back into the flow outputs

    No fallback behavior: if a cited chunk cannot be resolved, we fail.
    """
    _logger.info("Starting annotation enrichment (strict)")

    try:
        from forge_tools.clients import search_client
        from matsu_sdk.core.model.spatial.position_bbox import PositionBbox
    except ImportError as e:
        msg = f"Missing dependencies for annotation enrichment: {e}"
        raise RuntimeError(msg) from e

    # Collect content_ids referenced by flow outputs (single or multi question).
    # In Forge tooling, "<content_id: ...>" refers to DocumentStatementContent.id,
    # i.e. uuid5(f"{file_uuid}:{chunk_id}").
    content_ids: list[str] = []
    if "final_result" in flow_outputs:
        final_result = flow_outputs.get("final_result", {})
        content_ids = list(final_result.get("justifying_contents_ids", []) or [])
    elif "answers" in flow_outputs:
        for answer in flow_outputs.get("answers", []) or []:
            content_ids.extend(list(answer.get("justifying_contents_ids", []) or []))

    if not content_ids:
        _logger.info("No justifying_contents_ids found, skipping annotation enrichment")
        return flow_outputs

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique_content_ids = [x for x in content_ids if not (x in seen or seen.add(x))]

    # Index chunks by chunk.id across all source documents
    client = search_client()
    if getattr(client, "_session", None) is None:
        await client.start()

    def _content_id(document_id: str, chunk_id: str) -> str:
        # Matches pyclark_core.content.DocumentStatementContent.generate_uuid()
        return str(uuid.uuid5(uuid.NAMESPACE_OID, f"{document_id}:{chunk_id}"))

    def _doc_id_variants(raw_id: str) -> list[str]:
        """Return possible document_id strings used in DocumentStatementContent.

        In Forge tools, DocumentStatementContent.document_id is taken from file metadata `id`.
        Depending on upstream services, that can be:
        - bare UUID (e.g. df8b...)
        - an entity string (e.g. "id=UUID('df8b...') entity_type='FILE'")
        """
        variants: list[str] = []
        if raw_id:
            variants.append(raw_id)

        # If raw_id is an entity string, also include the extracted UUID.
        if "UUID('" in raw_id:
            try:
                extracted = raw_id.split("UUID('", 1)[1].split("')", 1)[0]
                if extracted and extracted not in variants:
                    variants.append(extracted)
            except Exception:
                pass

        # If raw_id looks like a bare UUID, also include the common entity string form.
        # (This matches what we saw in activity outputs: "id=UUID('...') entity_type='FILE'")
        if len(raw_id) == 36 and raw_id.count("-") == 4:
            entity = f"id=UUID('{raw_id}') entity_type='FILE'"
            if entity not in variants:
                variants.append(entity)

        return variants

    chunk_by_content_id: dict[str, tuple[object, str, str]] = {}
    remaining: set[str] = set(unique_content_ids)
    for f in source_files:
        file_uuid = getattr(f, "id", "") or ""
        file_checksum = getattr(f, "checksum", "") or ""
        file_name = getattr(f, "name", "") or ""
        if not file_uuid or not file_checksum:
            continue

        doc_id_candidates = _doc_id_variants(file_uuid)
        doc_chunks = await client.get_document_chunks(file_checksum)
        for ch in doc_chunks:
            if ch.id:
                for doc_id in doc_id_candidates:
                    cid = _content_id(doc_id, ch.id)
                    if cid in remaining:
                        chunk_by_content_id[cid] = (ch, file_uuid, file_name)
                        remaining.remove(cid)
                        if not remaining:
                            break
                if not remaining:
                    break
        if not remaining:
            break

    missing = sorted(remaining)
    if missing:
        msg = (
            "Could not resolve cited content ids from search service. "
            f"Missing {len(missing)}/{len(unique_content_ids)}: {missing[:10]}"
        )
        raise RuntimeError(msg)

    def _positions_list(chunk: object) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        meta = getattr(chunk, "meta_data", None)
        positions = getattr(meta, "positions", None) if meta else None
        if not positions:
            return out
        # positions is typically a dict[str, Position] (matsu_sdk types)
        for pos in positions.values():
            if isinstance(pos, PositionBbox) and getattr(pos, "bbox", None):
                bbox = pos.bbox
                out.append(
                    {
                        "bboxPosition": {
                            "bbox": {
                                "x0": float(bbox.x0),
                                "y0": float(bbox.y0),
                                "x1": float(bbox.x1),
                                "y1": float(bbox.y1),
                            },
                            "pageNumber": int(pos.page_number),
                        },
                    },
                )
        return out

    def _build_annotations_for(
        content_ids_in_order: list[str],
    ) -> tuple[list[dict[str, Any]], list[str]]:
        annotations: list[dict[str, Any]] = []
        citation_ids: list[str] = []
        for cid in content_ids_in_order:
            chunk, file_uuid, file_name = chunk_by_content_id[cid]
            citation_ids.append(cid)
            annotations.append(
                {
                    "id": cid,
                    "documentStatement": {
                        "documentId": file_uuid,
                        "documentName": file_name,
                        "content": getattr(chunk, "content", "") or "",
                        "positions": _positions_list(chunk),
                    },
                },
            )
        return annotations, citation_ids

    # Enrich flow outputs (single vs multi question)
    if "final_result" in flow_outputs:
        final_result = flow_outputs.get("final_result", {})
        ids_in_order = list(final_result.get("justifying_contents_ids", []) or [])
        annotations, citation_ids = _build_annotations_for(ids_in_order)
        flow_outputs["final_result"]["annotations"] = annotations
        flow_outputs["final_result"]["citation_annotation_ids"] = citation_ids
        _logger.info("Added %d annotations to final_result", len(annotations))

    if "answers" in flow_outputs:
        for answer in flow_outputs.get("answers", []) or []:
            ids_in_order = list(answer.get("justifying_contents_ids", []) or [])
            annotations, citation_ids = _build_annotations_for(ids_in_order)
            answer["annotations"] = annotations
            answer["citation_annotation_ids"] = citation_ids

    return flow_outputs


class CustomWorkflowActivity:
    """Temporal activity that runs Forge flows for CustomWorkflow processing."""

    _flow_loader: FlowLoader

    def __init__(self) -> None:
        self._flow_loader = FlowLoader()

    @activity.defn
    async def process(
        self,
        ctx: WorkflowContext,
        task_config: CustomWorkflowConfig,
    ) -> CustomWorkflowOutput:
        """Main activity entry - runs a Forge flow.

        Supports:
          - task_config.workflow_id (named flow)
          - task_config.additional_inputs (inline flow JSON or params)
          - fallback to default 'qa_default' flow
        """
        _logger.info(
            "CustomWorkflowActivity.process(job_id=%s) with workflow_id=%s",
            ctx.id,
            task_config.workflow_id or "qa_default",
        )
        _logger.info(
            "  - first_source_files: %d, second_source_files: %d, questions: %d",
            len(task_config.first_source_files),
            len(task_config.second_source_files),
            len(task_config.questions),
        )

        # 1) Resolve flow (inline vs named)
        flow_dict, additional_params = self._resolve_flow_and_params(task_config)

        # 2) Build flow inputs with custom workflow convention
        flow_inputs = InputMapper.build_custom_workflow_inputs(
            first_source_files=list(task_config.first_source_files),
            second_source_files=list(task_config.second_source_files),
            questions=list(task_config.questions),
            additional_params=additional_params,
        )

        # 3) Prepare authentication headers and execution context
        elise_api_headers = dict(ctx.headers) if ctx.headers else {}
        _logger.info("Authentication headers available: %s", list(elise_api_headers.keys()))

        execution_context = ExecutionContext(
            run_id=f"custom-workflow-{ctx.id}",
            elise_api_headers=elise_api_headers,
        )

        # 4) Execute flow with TemporalRuntime
        # Import here to avoid circular dependencies and ensure forge_tools are loaded
        try:
            from forge.execution.runtime import TemporalRuntime
            from forge.models import Flow
            from forge_tools.populated_registry import registry as forge_registry

            _logger.info("Using registry with %d tools", len(forge_registry._functions))
        except ImportError as e:
            _logger.error("Failed to import forge components: %s", e)
            _logger.error("Make sure forge and forge_tools are installed")
            error_msg = f"Failed to import forge components: {e}"
            raise RuntimeError(error_msg) from e

        # Convert flow dict to Flow object (Pydantic model)
        flow = Flow(**flow_dict)

        runtime = TemporalRuntime(registry=forge_registry)
        try:
            result = await runtime.run(
                flow=flow,
                inputs=flow_inputs,
                execution_context=execution_context,
            )
        except Exception as e:
            _logger.exception("Forge flow execution failed: %s", e)
            error_msg = f"Forge flow execution failed: {e}"
            raise RuntimeError(error_msg) from e
        finally:
            await runtime.cleanup()

        _logger.info(
            "Forge flow %s completed with status %s",
            flow.flow_id,
            result.status,
        )

        if result.status != "succeeded":
            error_msg = f"Forge flow failed with status {result.status}: {result.error}"
            _logger.error(error_msg)
            raise RuntimeError(error_msg)

        # 5) Enrich outputs with annotation data from search service
        enriched_outputs = await _enrich_with_annotations(
            flow_outputs=result.outputs,
            source_files=[
                *list(task_config.first_source_files),
                *list(task_config.second_source_files),
            ],
        )

        # 6) Map outputs to QuestionAnswer list
        answers = OutputMapper.to_question_answers(
            flow_outputs=enriched_outputs,
            original_questions=list[Question](task_config.questions),
        )

        return CustomWorkflowOutput(answers=answers)

    def _resolve_flow_and_params(
        self,
        cfg: CustomWorkflowConfig,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Determine which Flow to use and extract additional params.

        Priority:
        1. Inline flow in additional_inputs (JSON with 'flow_id', 'steps', etc.)
        2. Named flow via workflow_id
        3. Default flow (qa_default)

        Returns
        -------
            (flow_dict, additional_params)
        """
        additional_params: dict[str, Any] = {}

        # Parse additional_inputs
        if cfg.additional_inputs:
            try:
                data = json.loads(cfg.additional_inputs)
                _logger.info("Parsed additional_inputs: %s", data)

                # Detect if it's an inline flow (has flow_id and steps)
                if "flow_id" in data and "steps" in data:
                    _logger.info("Using inline flow from additional_inputs")
                    return data, {}

                # Otherwise, treat as additional params
                additional_params = data
                _logger.info("Using additional_inputs as params: %s", additional_params)
            except json.JSONDecodeError as e:
                _logger.error("Failed to parse additional_inputs as JSON: %s", e)

        # Use workflow_id or default
        flow_name = cfg.workflow_id or "qa_default"
        _logger.info("Loading named flow: %s", flow_name)
        flow_dict = self._flow_loader.load_by_name(flow_name)

        return flow_dict, additional_params
