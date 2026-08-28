from pathlib import Path

from agent_eval_mutation_lab.engine.canonical import source_tree_digest


def test_source_digest_excludes_only_declared_optional_subsystems(
    tmp_path: Path,
) -> None:
    package = tmp_path / "package"
    optional = package / "model_study"
    core = package / "engine"
    optional.mkdir(parents=True)
    core.mkdir()
    (package / "models.py").write_text("VALUE = 1\n", encoding="utf-8")
    (core / "runner.py").write_text("VALUE = 2\n", encoding="utf-8")
    (optional / "runner.py").write_text("VALUE = 3\n", encoding="utf-8")

    baseline = source_tree_digest(
        package, excluded_directories={"model_study"}
    )
    (optional / "runner.py").write_text("VALUE = 4\n", encoding="utf-8")
    assert (
        source_tree_digest(package, excluded_directories={"model_study"})
        == baseline
    )

    (core / "runner.py").write_text("VALUE = 5\n", encoding="utf-8")
    assert (
        source_tree_digest(package, excluded_directories={"model_study"})
        != baseline
    )
