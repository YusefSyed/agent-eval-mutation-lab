import json

from agent_eval_mutation_lab.benchmark import run_benchmark
from agent_eval_mutation_lab.report import render_markdown, write_reports


def test_benchmark_is_deterministic_and_nontrivial(tmp_path) -> None:
    first = run_benchmark()
    second = run_benchmark()
    assert first == second
    assert first["case_count"] == 13

    substantive = {
        name: summary
        for name, summary in first["scorers"].items()
        if name in {"attempted_call", "final_state", "receipt_aware"}
    }
    assert len({summary["accuracy"] for summary in substantive.values()}) > 1
    assert substantive["receipt_aware"]["accuracy"] > substantive["attempted_call"][
        "accuracy"
    ]

    json_path, markdown_path = write_reports(first, tmp_path)
    assert json.loads(json_path.read_text()) == first
    assert markdown_path.read_text() == render_markdown(first)

