"""Provider-neutral model task routing and canonical result delivery."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum


class StructuredOutputMode(str, Enum):
    STRICT_SCHEMA = "strict-schema"
    TOOL_CALL = "tool-call"
    JSON_OBJECT = "json-object"
    TEXT = "text"


@dataclass(frozen=True)
class ProviderCapabilities:
    provider_id: str
    model_id: str
    local: bool
    structured_output_modes: tuple[StructuredOutputMode, ...]

    def __post_init__(self) -> None:
        if not self.provider_id.strip() or not self.model_id.strip():
            raise ValueError("provider and model identities are required")
        if (
            not isinstance(self.structured_output_modes, tuple)
            or not self.structured_output_modes
            or any(
                not isinstance(mode, StructuredOutputMode)
                for mode in self.structured_output_modes
            )
        ):
            raise ValueError("at least one typed output mode is required")


class ModelTaskKind(str, Enum):
    LIVING_MEMORY_ANALYSIS = "living-memory-analysis"
    KNOWLEDGE_ANALYSIS = "knowledge-analysis"
    RELATIONSHIP_ANALYSIS = "relationship-analysis"
    PARTICIPANT_GOAL_CLASSIFICATION = "participant-goal-classification"
    PARTICIPANT_GOAL_REPLY = "participant-goal-reply"
    SITUATED_STATE_CLASSIFICATION = "situated-state-classification"
    SITUATED_STATE_REPLY = "situated-state-reply"
    MEDIUM_STATE_CLASSIFICATION = "medium-state-classification"
    MEDIUM_STATE_REPLY = "medium-state-reply"
    SOURCE_CHARACTER_EXTRACTION = "source-character-extraction"


@dataclass(frozen=True)
class ModelTask:
    kind: ModelTaskKind
    payload: object


@dataclass(frozen=True)
class ModelResult:
    kind: ModelTaskKind
    value: object


class ModelGatewayFailure(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class ProviderAdapter(ABC):
    """True-external provider Port; implementations own wire protocols."""

    capabilities: ProviderCapabilities

    @abstractmethod
    def invoke(self, task: ModelTask) -> ModelResult:
        raise NotImplementedError


class ModelGateway:
    """One small Interface for all bounded model tasks."""

    def __init__(self, adapter: ProviderAdapter) -> None:
        if not isinstance(adapter, ProviderAdapter):
            raise TypeError("adapter must implement ProviderAdapter")
        if not isinstance(adapter.capabilities, ProviderCapabilities):
            raise TypeError("adapter capabilities must be typed")
        self.capabilities = adapter.capabilities
        self._adapter = adapter

    def execute(self, task: ModelTask) -> ModelResult:
        if not isinstance(task, ModelTask) or not isinstance(task.kind, ModelTaskKind):
            raise ModelGatewayFailure("typed-model-task-required")
        try:
            result = self._adapter.invoke(task)
        except ModelGatewayFailure:
            raise
        except Exception as error:
            raise ModelGatewayFailure("provider-task-failed") from error
        if not isinstance(result, ModelResult) or result.kind is not task.kind:
            raise ModelGatewayFailure("provider-result-kind-mismatch")
        return result


__all__ = [
    "ModelGateway",
    "ModelGatewayFailure",
    "ModelResult",
    "ModelTask",
    "ModelTaskKind",
    "ProviderAdapter",
    "ProviderCapabilities",
    "StructuredOutputMode",
]
