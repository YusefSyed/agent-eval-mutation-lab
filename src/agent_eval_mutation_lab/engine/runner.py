"""Reference sequential execution and post-score validation."""

from __future__ import annotations

from collections.abc import Mapping

from agent_eval_mutation_lab.engine.contracts import (
    PlannedTask,
    PluginContractError,
    RunPlan,
    ScoreResult,
    ScorerInput,
    TaskContext,
    TaskRecord,
    ValidationResult,
)
from agent_eval_mutation_lab.engine.plugins import (
    ScorerPlugin,
    default_scorer_plugins,
)
from agent_eval_mutation_lab.models import Prediction


def validate_score(
    *, expected: Prediction, score: ScoreResult
) -> ValidationResult:
    prediction = score.prediction
    return ValidationResult(
        expected=expected,
        prediction=prediction,
        correct=prediction == expected,
        false_safe=prediction is False and expected is True,
        false_success=prediction is True and expected is False,
        unsupported_safe=prediction is False and expected is None,
        unsupported_success=prediction is True and expected is None,
    )


def score_worker_projection(
    *,
    scorer_id: str,
    scorer_input: ScorerInput,
    context: TaskContext,
    plugins: Mapping[str, ScorerPlugin],
) -> ScoreResult:
    """Call a scorer with only its explicit worker projection."""

    score = plugins[scorer_id].score(scorer_input, context=context)
    if score.prediction is not None and type(score.prediction) is not bool:
        raise PluginContractError(
            f"{scorer_id} returned invalid prediction {score.prediction!r}"
        )
    return score


def run_task(
    task: PlannedTask, *, plugins: Mapping[str, ScorerPlugin]
) -> TaskRecord:
    score = score_worker_projection(
        scorer_id=task.worker.scorer_id,
        scorer_input=task.worker.scorer_input,
        context=task.worker.context,
        plugins=plugins,
    )
    return TaskRecord(
        ordinal=task.worker.context.ordinal,
        task_key=task.worker.context.task_key,
        task_seed=task.worker.context.seed,
        case_id=task.case_id,
        family=task.family,
        evidence_condition=task.evidence_condition,
        scorer_id=task.worker.scorer_id,
        validation=validate_score(
            expected=task.oracle.attack_success, score=score
        ),
    )


def run_sequential(
    plan: RunPlan,
    *,
    plugins: Mapping[str, ScorerPlugin] | None = None,
) -> tuple[TaskRecord, ...]:
    registry = plugins or default_scorer_plugins()
    return tuple(run_task(task, plugins=registry) for task in plan.tasks)
