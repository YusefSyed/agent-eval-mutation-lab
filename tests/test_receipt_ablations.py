from agent_eval_mutation_lab.receipt_ablations import run_receipt_ablations


def test_receipt_ablations_expose_evidence_dependence() -> None:
    report = run_receipt_ablations()
    ablations = report["ablations"]
    baseline = ablations["baseline"]
    no_receipts = ablations["remove_prohibited_receipts"]
    no_effects = ablations["remove_effect_records"]
    timeouts = ablations["replace_success_with_timeout"]

    assert baseline["false_safe_rate"] == 0.0
    assert no_receipts["abstention_rate"] > baseline["abstention_rate"]
    assert no_receipts["false_safe_rate"] == 0.0
    assert no_effects["false_safe_rate"] > baseline["false_safe_rate"]
    assert timeouts["abstention_rate"] > baseline["abstention_rate"]

