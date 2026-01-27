from clark_protos.models import file_pb2 as _file_pb2
from clark_protos.processors import questionAnswering_pb2 as _questionAnswering_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Iterable as _Iterable, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class ProcessorCustomWorkflowConfig(_message.Message):
    __slots__ = ("first_source_files", "second_source_files", "questions", "workflow_id", "additional_inputs", "collectionId")
    FIRST_SOURCE_FILES_FIELD_NUMBER: _ClassVar[int]
    SECOND_SOURCE_FILES_FIELD_NUMBER: _ClassVar[int]
    QUESTIONS_FIELD_NUMBER: _ClassVar[int]
    WORKFLOW_ID_FIELD_NUMBER: _ClassVar[int]
    ADDITIONAL_INPUTS_FIELD_NUMBER: _ClassVar[int]
    COLLECTIONID_FIELD_NUMBER: _ClassVar[int]
    first_source_files: _containers.RepeatedCompositeFieldContainer[_file_pb2.FileMetaData]
    second_source_files: _containers.RepeatedCompositeFieldContainer[_file_pb2.FileMetaData]
    questions: _containers.RepeatedCompositeFieldContainer[_questionAnswering_pb2.Question]
    workflow_id: str
    additional_inputs: str
    collectionId: str
    def __init__(self, first_source_files: _Optional[_Iterable[_Union[_file_pb2.FileMetaData, _Mapping]]] = ..., second_source_files: _Optional[_Iterable[_Union[_file_pb2.FileMetaData, _Mapping]]] = ..., questions: _Optional[_Iterable[_Union[_questionAnswering_pb2.Question, _Mapping]]] = ..., workflow_id: _Optional[str] = ..., additional_inputs: _Optional[str] = ..., collectionId: _Optional[str] = ...) -> None: ...

class ProcessorCustomWorkflowOutput(_message.Message):
    __slots__ = ("answers", "collectionId")
    ANSWERS_FIELD_NUMBER: _ClassVar[int]
    COLLECTIONID_FIELD_NUMBER: _ClassVar[int]
    answers: _containers.RepeatedCompositeFieldContainer[_questionAnswering_pb2.QuestionAnswer]
    collectionId: str
    def __init__(self, answers: _Optional[_Iterable[_Union[_questionAnswering_pb2.QuestionAnswer, _Mapping]]] = ..., collectionId: _Optional[str] = ...) -> None: ...
