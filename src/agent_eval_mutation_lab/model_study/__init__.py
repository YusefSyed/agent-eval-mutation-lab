"""Leakage-resistant contracts for a separately executed model study."""

from agent_eval_mutation_lab.model_study.contracts import (
    ModelConfig,
    ModelIdentity,
    StudyArm,
    TerminalStatus,
    TrialIdentity,
    TrialTerminal,
    build_trial_identity,
)
from agent_eval_mutation_lab.model_study.projection import (
    ModelInput,
    project_model_input,
)
from agent_eval_mutation_lab.model_study.schemas import (
    DIRECT_RESPONSE_SCHEMA,
    EVIDENCE_FIRST_RESPONSE_SCHEMA,
    DirectResponse,
    EvidenceFirstResponse,
    ExecutionAssessment,
    FinalStateAttribution,
    HarmAssessment,
    ProbabilityVector,
    Verdict,
)

__all__ = [
    "DIRECT_RESPONSE_SCHEMA",
    "EVIDENCE_FIRST_RESPONSE_SCHEMA",
    "DirectResponse",
    "ExecutionAssessment",
    "EvidenceFirstResponse",
    "FinalStateAttribution",
    "HarmAssessment",
    "ModelConfig",
    "ModelIdentity",
    "ModelInput",
    "StudyArm",
    "TerminalStatus",
    "TrialIdentity",
    "TrialTerminal",
    "ProbabilityVector",
    "Verdict",
    "build_trial_identity",
    "project_model_input",
]
