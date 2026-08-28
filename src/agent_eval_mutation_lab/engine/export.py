"""Canonical run exports and dependency-free static evidence report."""

from __future__ import annotations

import hashlib
import html
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from agent_eval_mutation_lab.engine.aggregation import aggregate_records
from agent_eval_mutation_lab.engine.canonical import (
    canonical_json_bytes,
    plugin_payload,
    run_spec_payload,
    sha256_bytes,
    task_record_payload,
)
from agent_eval_mutation_lab.engine.contracts import (
    ExecutionSummary,
    RunPlan,
    RunState,
    TaskRecord,
)
from agent_eval_mutation_lab.engine.plugins import ScorerPlugin


def results_jsonl(records: Sequence[TaskRecord]) -> bytes:
    ordered = sorted(records, key=lambda record: record.ordinal)
    return b"".join(
        canonical_json_bytes(task_record_payload(record)) for record in ordered
    )


def build_manifest(
    plan: RunPlan,
    summary: ExecutionSummary,
    *,
    plugins: Mapping[str, ScorerPlugin],
) -> dict[str, Any]:
    ordered = sorted(summary.records, key=lambda record: record.ordinal)
    record_digests = [
        {
            "ordinal": record.ordinal,
            "task_key": record.task_key,
            "result_digest": sha256_bytes(
                canonical_json_bytes(task_record_payload(record))
            ),
        }
        for record in ordered
    ]
    semantic_run_digest = sha256_bytes(
        canonical_json_bytes(
            {
                "run_key": plan.run_key,
                "task_results": record_digests,
            }
        )
    )
    result_bytes = results_jsonl(ordered)
    return {
        "schema_version": 1,
        "status": summary.state.value,
        "scope": "finite synthetic corpus; descriptive results only",
        "warning": (
            "Complete canonical run. No production-safety or population claim."
            if summary.state is RunState.COMPLETE
            else "INCOMPLETE RUN: aggregate conclusions are not qualified evidence."
        ),
        "run_key": plan.run_key,
        "semantic_run_digest": semantic_run_digest,
        "run_spec": run_spec_payload(plan.spec),
        "plugins": [
            plugin_payload(plugins[plugin_id].descriptor)
            for plugin_id in plan.spec.scorer_ids
        ],
        "expected_tasks": summary.expected_tasks,
        "completed_tasks": summary.completed_tasks,
        "failed_tasks": summary.failed_tasks,
        "canonical_record_count": len(ordered),
        "results_sha256": sha256_bytes(result_bytes),
        "task_results": record_digests,
        "operational_metadata_excluded": [
            "absolute_paths",
            "cache_hit_timing",
            "completion_order",
            "process_or_thread_ids",
            "sqlite_page_layout",
            "timestamps",
            "worker_count",
        ],
    }


def _percent(value: int | float | None) -> str:
    return "n/a" if value is None else f"{float(value) * 100:.1f}%"


def _metric_rows(records: Sequence[TaskRecord]) -> str:
    aggregates = aggregate_records(records)
    rows = []
    for condition, scorers in aggregates.items():
        for scorer_id, metrics in scorers.items():
            overclaims = int(metrics["unsupported_safe_count"] or 0) + int(
                metrics["unsupported_success_count"] or 0
            )
            rows.append(
                "<tr>"
                '<td data-label="Evidence condition">'
                f"{html.escape(condition.replace('_', ' '))}</td>"
                '<td data-label="Scorer"><code>'
                f"{html.escape(scorer_id)}</code></td>"
                '<td data-label="Tri-state accuracy">'
                f"{_percent(metrics['tri_state_accuracy'])}</td>"
                '<td data-label="Coverage">'
                f"{_percent(metrics['coverage_rate'])}</td>"
                '<td data-label="False safe">'
                f"{metrics['false_safe_count']}</td>"
                '<td data-label="False success">'
                f"{metrics['false_success_count']}</td>"
                '<td data-label="Unknown overclaims">'
                f"{overclaims}</td>"
                "</tr>"
            )
    return "\n".join(rows)


def render_html(
    manifest: dict[str, Any], records: Sequence[TaskRecord]
) -> str:
    state = str(manifest["status"])
    complete = state == RunState.COMPLETE.value
    status_class = "ok" if complete else "warn"
    status_label = "COMPLETE" if complete else "INCOMPLETE"
    unique_cases = len({record.case_id for record in records})
    unique_families = len({record.family for record in records})
    unique_conditions = len({record.evidence_condition for record in records})
    run_key = html.escape(str(manifest["run_key"]))
    semantic_digest = html.escape(str(manifest["semantic_run_digest"]))
    results_digest = html.escape(str(manifest["results_sha256"]))
    rows = _metric_rows(records)
    warning = html.escape(str(manifest["warning"]))
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="dark">
  <title>Agent Eval Mutation Lab — Evidence Report</title>
  <style>
    :root {{
      --bg: #071014;
      --panel: #0e1b21;
      --panel-2: #13262d;
      --text: #eef8f6;
      --muted: #9db7b3;
      --accent: #65e6c4;
      --accent-2: #80aaff;
      --warning: #ffc46b;
      --line: #29434a;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background:
        radial-gradient(circle at 10% 0%, #123a3a 0, transparent 32rem),
        var(--bg);
      color: var(--text);
      font: 16px/1.6 ui-sans-serif, system-ui, sans-serif;
    }}
    a {{ color: var(--accent); }}
    code {{ font-family: ui-monospace, SFMono-Regular, monospace; }}
    .skip {{ position: absolute; left: -9999px; }}
    .skip:focus {{ left: 1rem; top: 1rem; z-index: 3; }}
    .wrap {{ width: min(1160px, calc(100% - 2rem)); margin: auto; }}
    header {{ padding: 5rem 0 2rem; }}
    .eyebrow {{
      color: var(--accent);
      font-weight: 750;
      letter-spacing: .12em;
      text-transform: uppercase;
    }}
    h1 {{
      max-width: 900px;
      margin: .5rem 0 1rem;
      font-size: clamp(2.5rem, 7vw, 5.5rem);
      line-height: .98;
      letter-spacing: -.055em;
    }}
    .lede {{ max-width: 760px; color: var(--muted); font-size: 1.15rem; }}
    .status {{
      display: inline-flex;
      gap: .5rem;
      align-items: center;
      margin-top: 1rem;
      padding: .45rem .8rem;
      border: 1px solid var(--line);
      border-radius: 999px;
      background: var(--panel);
      font-weight: 750;
    }}
    .status.ok {{ color: var(--accent); }}
    .status.warn {{ color: var(--warning); }}
    main {{ padding-bottom: 5rem; }}
    section {{ margin-top: 1.25rem; padding: 1.5rem; }}
    .panel {{
      border: 1px solid var(--line);
      border-radius: 1.2rem;
      background: linear-gradient(145deg, var(--panel), var(--panel-2));
      box-shadow: 0 24px 60px #0005;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(165px, 1fr));
      gap: .8rem;
    }}
    .stat {{ padding: 1rem; border-left: 3px solid var(--accent-2); }}
    .stat strong {{ display: block; font-size: 2rem; line-height: 1.1; }}
    .stat span {{ color: var(--muted); }}
    h2 {{ margin-top: 0; font-size: 1.6rem; }}
    h3 {{ margin-bottom: .3rem; color: var(--accent); }}
    .table-wrap {{ overflow-x: auto; }}
    table {{ width: 100%; border-collapse: collapse; min-width: 850px; }}
    caption {{ text-align: left; color: var(--muted); padding-bottom: .8rem; }}
    th, td {{ padding: .7rem; border-bottom: 1px solid var(--line); }}
    th {{ text-align: left; color: var(--muted); font-size: .85rem; }}
    td:not(:first-child):not(:nth-child(2)) {{ font-variant-numeric: tabular-nums; }}
    .pipeline {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(145px, 1fr));
      gap: .65rem;
      list-style: none;
      padding: 0;
    }}
    .pipeline li {{
      min-height: 7rem;
      padding: 1rem;
      border: 1px solid var(--line);
      border-radius: .8rem;
      background: #07101499;
    }}
    .pipeline b {{ display: block; color: var(--accent-2); }}
    .hash {{
      overflow-wrap: anywhere;
      padding: .8rem;
      background: #050b0e;
      border-radius: .6rem;
      color: var(--muted);
    }}
    .warning {{ border-left: 4px solid var(--warning); }}
    details {{ margin-top: .8rem; }}
    summary {{ cursor: pointer; color: var(--accent); font-weight: 700; }}
    footer {{ padding: 2rem 0 4rem; color: var(--muted); }}
    @media (max-width: 620px) {{
      header {{ padding-top: 3rem; }}
      section {{ padding: 1rem; }}
      table {{ min-width: 0; }}
      thead {{
        position: absolute;
        width: 1px;
        height: 1px;
        overflow: hidden;
        clip-path: inset(50%);
      }}
      tbody, tr, td {{ display: block; }}
      tbody tr {{
        margin-top: .85rem;
        padding: .7rem;
        border: 1px solid var(--line);
        border-radius: .75rem;
        background: #07101499;
      }}
      td {{
        display: grid;
        grid-template-columns: minmax(7.5rem, .8fr) minmax(0, 1.2fr);
        gap: .75rem;
        padding: .35rem;
        border: 0;
        overflow-wrap: anywhere;
      }}
      td::before {{
        content: attr(data-label);
        color: var(--muted);
        font-size: .8rem;
        font-weight: 700;
      }}
    }}
  </style>
</head>
<body>
  <a class="skip" href="#results">Skip to results</a>
  <header class="wrap">
    <div class="eyebrow">Execution-semantic scorer evaluation</div>
    <h1>Did the attack execute—or was it only attempted?</h1>
    <p class="lede">
      A typed, deterministic, resumable Python engine tests whether tool-agent
      scorers preserve the boundary between proposals, execution evidence,
      realized harm, and justified uncertainty.
    </p>
    <div class="status {status_class}">{status_label} · {warning}</div>
  </header>
  <main class="wrap">
    <section class="grid" aria-label="Run summary">
      <div class="panel stat">
        <strong>{len(records)}</strong><span>canonical tasks</span>
      </div>
      <div class="panel stat">
        <strong>{unique_cases}</strong><span>synthetic cases</span>
      </div>
      <div class="panel stat">
        <strong>{unique_families}</strong><span>scenario families</span>
      </div>
      <div class="panel stat">
        <strong>{unique_conditions}</strong><span>evidence conditions</span>
      </div>
    </section>

    <section class="panel" id="results">
      <h2>Finite-corpus results</h2>
      <div class="table-wrap">
        <table>
          <caption>
            Exact descriptive metrics. These are not confidence intervals or
            population estimates.
          </caption>
          <thead>
            <tr>
              <th>Evidence condition</th><th>Scorer</th>
              <th>Tri-state accuracy</th><th>Coverage</th>
              <th>False safe</th><th>False success</th><th>Unknown overclaims</th>
            </tr>
          </thead>
          <tbody>{rows}</tbody>
        </table>
      </div>
    </section>

    <section class="panel">
      <h2>Information-flow architecture</h2>
      <ol class="pipeline">
        <li><b>1 · Plan</b>Immutable RunSpec creates 104 content-keyed tasks.</li>
        <li><b>2 · Project</b>Oracle-only fields are removed before scoring.</li>
        <li><b>3 · Score</b>Explicit typed plugins return true, false, or unknown.</li>
        <li><b>4 · Validate</b>The coordinator rejoins finalized scores with truth.</li>
        <li><b>5 · Commit</b>One writer records immutable results transactionally.</li>
        <li><b>6 · Export</b>Canonical order erases worker scheduling noise.</li>
      </ol>
      <details>
        <summary>Why no async service or distributed scheduler?</summary>
        <p>
          The benchmark is offline and the measured 104-task workload is tiny.
          Bounded threads exist to test schedule independence, not to claim speed.
          A network service, generic event sourcing, or mandatory async API would
          add surface area without stronger evidence.
        </p>
      </details>
    </section>

    <section class="panel">
      <h2>Reproducibility identity</h2>
      <h3>Run key</h3><div class="hash"><code>{run_key}</code></div>
      <h3>Semantic run digest</h3>
      <div class="hash"><code>{semantic_digest}</code></div>
      <h3>Canonical results SHA-256</h3>
      <div class="hash"><code>{results_digest}</code></div>
      <p>
        Worker count, completion order, cache timing, absolute paths, timestamps,
        and SQLite page layout are deliberately excluded from semantic identity.
      </p>
    </section>

    <section class="panel warning">
      <h2>Claim boundary</h2>
      <p>
        This report covers a hand-authored finite synthetic corpus. It does not
        estimate real-world model behavior, validate a production framework,
        establish general safety, or prove unaided Python authorship.
      </p>
    </section>
  </main>
  <footer class="wrap">
    Agent Eval Mutation Lab · static report · no network or external assets
  </footer>
</body>
</html>
"""


def _write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def write_run_artifacts(
    plan: RunPlan,
    summary: ExecutionSummary,
    output_dir: Path,
    *,
    plugins: Mapping[str, ScorerPlugin],
) -> tuple[Path, Path, Path, Path]:
    result_bytes = results_jsonl(summary.records)
    manifest = build_manifest(plan, summary, plugins=plugins)
    manifest_bytes = json.dumps(
        manifest, indent=2, sort_keys=True, ensure_ascii=False
    ).encode() + b"\n"
    report_bytes = render_html(manifest, summary.records).encode()

    results_path = output_dir / "results.jsonl"
    manifest_path = output_dir / "run-manifest.json"
    report_path = output_dir / "report.html"
    sums_path = output_dir / "SHA256SUMS"
    _write(results_path, result_bytes)
    _write(manifest_path, manifest_bytes)
    _write(report_path, report_bytes)

    sums = []
    for path in (manifest_path, report_path, results_path):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        sums.append(f"{digest}  {path.name}")
    _write(sums_path, ("\n".join(sums) + "\n").encode())
    return results_path, manifest_path, report_path, sums_path
