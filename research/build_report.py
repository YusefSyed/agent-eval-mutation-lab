from __future__ import annotations

import json
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "artifacts/latest/results.json"
OUTPUT = (
    ROOT
    / "output/pdf/Agent_Eval_Mutation_Lab_Research_and_Build_Decision_2026-08-28.pdf"
)

NAVY = colors.HexColor("#102A43")
BLUE = colors.HexColor("#1F5A94")
TEAL = colors.HexColor("#167D7F")
PALE = colors.HexColor("#EAF2F8")
LIGHT = colors.HexColor("#F5F7FA")
INK = colors.HexColor("#1F2933")
MUTED = colors.HexColor("#52616B")
RULE = colors.HexColor("#CBD5E1")


def link(label: str, url: str) -> str:
    return f'<link href="{url}" color="#1F5A94"><u>{label}</u></link>'


def styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "TitleCustom",
            parent=base["Title"],
            fontName="Helvetica-Bold",
            fontSize=25,
            leading=29,
            textColor=NAVY,
            alignment=TA_CENTER,
            spaceAfter=12,
        ),
        "subtitle": ParagraphStyle(
            "Subtitle",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=11,
            leading=16,
            textColor=MUTED,
            alignment=TA_CENTER,
            spaceAfter=16,
        ),
        "h1": ParagraphStyle(
            "H1",
            parent=base["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=16,
            leading=20,
            textColor=NAVY,
            spaceBefore=8,
            spaceAfter=8,
        ),
        "h2": ParagraphStyle(
            "H2",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=11.5,
            leading=14,
            textColor=BLUE,
            spaceBefore=8,
            spaceAfter=5,
        ),
        "body": ParagraphStyle(
            "Body",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=9.5,
            leading=13.5,
            textColor=INK,
            spaceAfter=7,
        ),
        "small": ParagraphStyle(
            "Small",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=8,
            leading=11,
            textColor=MUTED,
            spaceAfter=4,
        ),
        "callout": ParagraphStyle(
            "Callout",
            parent=base["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=10,
            leading=14,
            textColor=NAVY,
            leftIndent=10,
            rightIndent=10,
            spaceBefore=6,
            spaceAfter=6,
        ),
        "bullet": ParagraphStyle(
            "BulletCustom",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=9,
            leading=12.5,
            textColor=INK,
            leftIndent=14,
            firstLineIndent=-8,
            spaceAfter=4,
        ),
        "table": ParagraphStyle(
            "TableText",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=7.5,
            leading=10,
            textColor=INK,
        ),
        "table_header": ParagraphStyle(
            "TableHeader",
            parent=base["BodyText"],
            fontName="Helvetica-Bold",
            fontSize=7.5,
            leading=9.5,
            textColor=colors.white,
        ),
    }


def para(text: str, style: ParagraphStyle) -> Paragraph:
    return Paragraph(text, style)


def bullet(text: str, style: ParagraphStyle) -> Paragraph:
    return Paragraph(f"- {text}", style)


def add_page_number(canvas, doc) -> None:  # type: ignore[no-untyped-def]
    canvas.saveState()
    width, height = letter
    canvas.setStrokeColor(RULE)
    canvas.setLineWidth(0.5)
    canvas.line(0.65 * inch, 0.52 * inch, width - 0.65 * inch, 0.52 * inch)
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(MUTED)
    canvas.drawString(0.65 * inch, 0.33 * inch, "Agent Eval Mutation Lab")
    canvas.drawRightString(
        width - 0.65 * inch, 0.33 * inch, f"Page {doc.page} | 2026-08-28"
    )
    canvas.restoreState()


def metric_table(report: dict, s: dict[str, ParagraphStyle]) -> Table:
    header = [
        para("Scorer", s["table_header"]),
        para("Accuracy", s["table_header"]),
        para("False success", s["table_header"]),
        para("False safe", s["table_header"]),
        para("Abstain", s["table_header"]),
        para("Changing", s["table_header"]),
        para("Invariance", s["table_header"]),
    ]
    rows = [header]
    names = [
        "attempted_call",
        "final_state",
        "receipt_aware",
        "always_safe",
        "always_attack",
        "always_abstain",
    ]
    for name in names:
        item = report["scorers"][name]
        rows.append(
            [
                para(name.replace("_", " "), s["table"]),
                f"{item['accuracy']:.3f}",
                f"{item['false_success_rate']:.3f}",
                f"{item['false_safe_rate']:.3f}",
                f"{item['abstention_rate']:.3f}",
                f"{item['label_changing_semantic_score']:.3f}",
                f"{item['label_preserving_invariance']:.3f}",
            ]
        )
    table = Table(
        rows,
        colWidths=[1.2 * inch, 0.72 * inch, 0.83 * inch, 0.72 * inch, 0.62 * inch, 0.72 * inch, 0.72 * inch],
        repeatRows=1,
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("FONTSIZE", (1, 1), (-1, -1), 7.5),
                ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
                ("GRID", (0, 0), (-1, -1), 0.35, RULE),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table


def evidence_table(s: dict[str, ParagraphStyle]) -> Table:
    rows = [
        [
            para("Verified evidence", s["table_header"]),
            para("Implication", s["table_header"]),
        ],
        [
            para("Current named projects are TypeScript, JavaScript, or Deno.", s["table"]),
            para("Python is asserted in Skills but lacks a named flagship artifact.", s["table"]),
        ],
        [
            para("Anthropic, Scale, Quadrillion, and agent-platform roles name Python, empirical work, evals, or agent tooling.", s["table"]),
            para("A Python evaluation artifact closes a cross-role gap rather than a single-posting keyword gap.", s["table"]),
        ],
        [
            para("Inspect AI, ControlArena, and AgentDojo are active MIT-licensed Python ecosystems.", s["table"]),
            para("Use them later as dependencies or adapters; do not fork and lightly restyle them.", s["table"]),
        ],
        [
            para("Agent Security Gate already covers argument-aware enforcement and related benchmarks.", s["table"]),
            para("The first project idea was rejected as overlapping prior art.", s["table"]),
        ],
        [
            para("AgentDojo issue #168 documents attempted-but-blocked calls scored as success.", s["table"]),
            para("Motivates scorer validation, but the issue and reproduction are not an original discovery.", s["table"]),
        ],
    ]
    table = Table(rows, colWidths=[3.2 * inch, 3.4 * inch], repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
                ("GRID", (0, 0), (-1, -1), 0.35, RULE),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return table


def build() -> Path:
    report = json.loads(RESULTS.read_text(encoding="utf-8"))
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    s = styles()
    doc = SimpleDocTemplate(
        str(OUTPUT),
        pagesize=letter,
        rightMargin=0.65 * inch,
        leftMargin=0.65 * inch,
        topMargin=0.58 * inch,
        bottomMargin=0.68 * inch,
        title="Agent Eval Mutation Lab - Research and Build Decision",
        author="Yusef Syed",
        subject="Python portfolio evidence, prior art, benchmark design, and verified first milestone",
    )
    story = []
    story.append(Spacer(1, 0.24 * inch))
    story.append(para("Agent Eval Mutation Lab", s["title"]))
    story.append(
        para(
            "Deep Research, GPT-5.6 Pro decision review, prior-art correction, and verified offline Python milestone",
            s["subtitle"],
        )
    )
    callout = Table(
        [[para("Decision: build a narrow scorer-mutation benchmark, not a copied framework, authorization-gate clone, or another consumer app.", s["callout"])]],
        colWidths=[6.55 * inch],
    )
    callout.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), PALE),
                ("BOX", (0, 0), (-1, -1), 1.0, TEAL),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story.extend([callout, Spacer(1, 10)])
    story.append(para("Executive answer", s["h1"]))
    story.append(
        para(
            "The current resume proves unusually broad product engineering, but Python is visible only in the skills list. Current target roles repeatedly combine production Python with evaluation, agent tooling, measurement, open source, or empirical work. The highest-leverage response is one original public Python artifact with a reproducible empirical question - not a fork-and-rename portfolio clone.",
            s["body"],
        )
    )
    story.append(
        para(
            "Two GPT-5.6 Pro reviews selected an offline, framework-independent benchmark architecture and then approved the concrete scorer-mutation subject after an earlier argument-aware authorization idea failed the prior-art gate. The selected project tests whether scorers preserve distinctions among proposed calls, actual execution, transient harm, final state, and missing receipts.",
            s["body"],
        )
    )
    story.append(para("What is verified today", s["h2"]))
    for item in [
        "13 synthetic cases across five scenario families and seven execution-semantic mutation types.",
        "Three substantive scorer contracts plus always-safe, always-attack, and always-abstain controls.",
        "Eight focused tests, Ruff, and strict mypy all pass.",
        "The run is offline, needs no API key, and emits deterministic JSON and Markdown reports.",
        "No real-model, framework-safety, production-safety, or independent-fluency claim is supported yet.",
    ]:
        story.append(bullet(item, s["bullet"]))

    story.append(PageBreak())
    story.append(para("1. Evidence and role alignment", s["h1"]))
    story.append(evidence_table(s))
    story.append(Spacer(1, 8))
    story.append(para("Role-source highlights", s["h2"]))
    story.append(
        para(
            f"{link('Anthropic Fellows', 'https://red.anthropic.com/2024/anthropic-fellows-program/')} names strong Python, empirical AI-safety research, independent execution, open source, and clear communication. {link('Scale AI Builder Intern', 'https://scale.com/careers/4703343005')} names production-quality Python and/or JavaScript, agentic workflows, LLM evals, measurement, and portfolio evidence. {link('Quadrillion', 'https://jobs.ashbyhq.com/quadrillion-labs/601e105d-2f0f-4482-9bae-3a825a1b97fd')} asks for significant engineering ability in Python or React while building an agentic research platform.",
            s["body"],
        )
    )
    story.append(para("Framework reuse decision", s["h2"]))
    story.append(
        para(
            f"{link('Inspect AI', 'https://inspect.aisi.org.uk/tasks.html')} supplies task, dataset, solver, scorer, and log abstractions. {link('ControlArena', 'https://github.com/UKGovernmentBEIS/control-arena')} supplies AI-control settings, protocols, monitors, scorers, and safety/usefulness analysis. {link('AgentDojo', 'https://github.com/ethz-spylab/agentdojo')} supplies realistic prompt-injection environments and programmatic scoring. All are strong later adapter targets. None should be copied wholesale merely to produce a resume project.",
            s["body"],
        )
    )

    story.append(para("2. Prior-art correction and research question", s["h1"]))
    story.append(
        para(
            f"The first proposed subject - argument-aware pre-execution authorization - was rejected after finding {link('Agent Security Gate', 'https://github.com/giselleevita/agent-security-gate')}, an Apache-2.0 Python project with policy enforcement, approvals, audit receipts, an 18-scenario benchmark, and an AgentDojo study.",
            s["body"],
        )
    )
    story.append(
        para(
            f"The revised subject is broader than reproducing {link('AgentDojo issue #168', 'https://github.com/ethz-spylab/agentdojo/issues/168')}: <b>Can execution-semantic mutation testing expose tool-agent scorers that confuse proposed actions, actual execution, and realized harm?</b>",
            s["body"],
        )
    )
    story.append(para("Honest originality boundary", s["h2"]))
    story.append(
        para(
            f"Mutation testing is established in {link('SWE-Mutation', 'https://arxiv.org/abs/2605.22175')}, {link('LLMorpheus', 'https://arxiv.org/abs/2404.09952')}, and recent semantic-evaluator work such as {link('Breaking Models to Test the Judge', 'https://arxiv.org/abs/2608.14315')}. The defensible claim is an adaptation to execution-semantic tool-agent scorers with an explicit outcome ontology and finite benchmark. It is not a first-ever mutation-testing claim or discovery of the AgentDojo bug.",
            s["body"],
        )
    )

    story.append(PageBreak())
    story.append(para("3. Benchmark design", s["h1"]))
    story.append(para("Outcome ontology", s["h2"]))
    for item in [
        "Unsafe attempt: a prohibited tool call was proposed.",
        "Unsafe execution: a prohibited call produced an actual successful or partial effect.",
        "Harmful side effect: the harm predicate became true at any point, including transiently.",
        "Harmful final state: the harm predicate remains true after the trajectory.",
        "Attack success: true for established harm, false for established no-harm, and unknown when a prohibited timeout leaves execution unresolved.",
    ]:
        story.append(bullet(item, s["bullet"]))
    story.append(para("Scorer contracts", s["h2"]))
    scorer_rows = [
        [para("Scorer", s["table_header"]), para("Declared contract and expected weakness", s["table_header"])],
        [para("Attempted call", s["table"]), para("Detect prohibited proposals. It is a deliberate contract mismatch when judged as successful harm and can inflate false-success counts.", s["table"])],
        [para("Final state", s["table"]), para("Detect harm in the final snapshot. It can miss transient or later-reversed side effects.", s["table"])],
        [para("Receipt aware", s["table"]), para("Replay scorer-visible execution receipts and abstain on missing or timed-out prohibited evidence. It is not an oracle and must survive receipt ablations.", s["table"])],
    ]
    scorer_table = Table(scorer_rows, colWidths=[1.25 * inch, 5.35 * inch], repeatRows=1)
    scorer_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
        ("GRID", (0, 0), (-1, -1), 0.35, RULE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(scorer_table)
    story.append(Spacer(1, 8))
    story.append(para("Mutation families", s["h2"]))
    story.append(
        para(
            "Denied, failed, timed-out, missing-receipt, duplicated, reordered, and partial executions are represented. The corpus includes label-changing mutations, label-preserving negative controls, and evidence-withholding cases that are excluded from invariance scoring when abstention is the honest response.",
            s["body"],
        )
    )
    story.append(para("Primary falsification tests", s["h2"]))
    for item in [
        "Match each scorer to its declared target; do not manufacture failure by judging attempt detection as success detection without saying so.",
        "Require invariance on label-preserving mutations as well as sensitivity on label-changing mutations.",
        "Prevent scorers from reading expected labels, mutation names, actual execution fields, or case IDs.",
        "Freeze initial scorers before a held-out or separately authored mutation family.",
        "Ablate receipt status, side-effect records, ordering metadata, missing receipts, and contradictory evidence.",
    ]:
        story.append(bullet(item, s["bullet"]))

    story.append(PageBreak())
    story.append(para("4. Verified first milestone", s["h1"]))
    story.append(metric_table(report, s))
    story.append(Spacer(1, 8))
    story.append(para("What the finite results show", s["h2"]))
    for item in [
        "Attempted-call scoring has 0.667 accuracy and a 0.333 false-success rate against the attack-success target. This diagnoses a contract mismatch, not a flaw in attempt detection itself.",
        "Final-state scoring reaches 0.917 accuracy but misses transient harm and has 0.500 invariance across the two label-preserving pairs.",
        "Receipt-aware scoring reaches 0.917 accuracy with zero false-success and false-safe rates, 1.000 label-changing score, and 1.000 invariance; it abstains on one known-label case with a missing harmful receipt.",
        "Always-safe and always-attack controls each reach 0.500 accuracy, exposing the balanced known-label corpus. Always-abstain has zero accuracy and full abstention.",
    ]:
        story.append(bullet(item, s["bullet"]))
    story.append(para("Verification receipt", s["h2"]))
    receipt = Table(
        [
            [para("Check", s["table_header"]), para("Observed outcome", s["table_header"])],
            [para("pytest", s["table"]), para("8 passed", s["table"])],
            [para("Ruff", s["table"]), para("All checks passed", s["table"])],
            [para("mypy --strict", s["table"]), para("No issues in 10 source files", s["table"])],
            [para("Offline report", s["table"]), para("Deterministic JSON and Markdown generated with no API key", s["table"])],
            [para("Results JSON SHA-256", s["table"]), para("b7ad1de4c15cabd64360c55e2ba451ecc813d8e3a3abe1dfac904589234ef093", s["small"])],
        ],
        colWidths=[1.55 * inch, 5.05 * inch],
        repeatRows=1,
    )
    receipt.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
        ("GRID", (0, 0), (-1, -1), 0.35, RULE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(receipt)

    story.append(PageBreak())
    story.append(para("5. Limitations and next gates", s["h1"]))
    for item in [
        "The cases are hand-authored synthetic fixtures. Exact finite-corpus results do not estimate real-world model or framework behavior.",
        "The receipt-aware scorer is favored by the ontology and must survive non-circular receipt ablations and held-out mutations.",
        "Mutants derived from one base case are correlated. Any later bootstrap must resample scenario families and be described only as corpus-sensitivity analysis.",
        "One real-log adapter is required before claiming framework relevance, and only if public logs expose the necessary execution evidence.",
        "Independent label review and a protected no-AI ownership gate remain uncompleted.",
    ]:
        story.append(bullet(item, s["bullet"]))
    story.append(para("Required next milestone", s["h2"]))
    for item in [
        "Freeze the current corpus and scorers.",
        "Add one held-out or separately authored mutation family.",
        "Predeclare receipt-field ablations and leave-one-family-out sensitivity.",
        "Obtain independent case-label review.",
        "Add one thin Inspect or AgentDojo adapter without changing the core.",
        "Complete the separate changed-contract, seeded-debugging, explanation, and clean-reproduction ownership gate.",
    ]:
        story.append(bullet(item, s["bullet"]))
    story.append(
        KeepTogether(
            [
                para("Claim boundary", s["h2"]),
                para(
                    "Truthful current phrasing: Codex-assisted offline Python benchmark kernel with deterministic synthetic results. Unsupported phrasing: independently built proof of Python fluency, first-ever mutation benchmark, proof that a framework is unsafe, or completed empirical research study.",
                    s["callout"],
                ),
            ]
        )
    )

    story.append(PageBreak())
    story.append(para("Sources", s["h1"]))
    sources = [
        ("Anthropic", "Introducing the Anthropic Fellows Program", "https://red.anthropic.com/2024/anthropic-fellows-program/"),
        ("Scale AI", "AI Builder Intern", "https://scale.com/careers/4703343005"),
        ("Quadrillion", "Software Engineering Intern", "https://jobs.ashbyhq.com/quadrillion-labs/601e105d-2f0f-4482-9bae-3a825a1b97fd"),
        ("UK AI Security Institute", "Inspect AI tasks and log documentation", "https://inspect.aisi.org.uk/tasks.html"),
        ("UK AI Security Institute and Redwood Research", "ControlArena", "https://github.com/UKGovernmentBEIS/control-arena"),
        ("ETH Zurich SPY Lab and collaborators", "AgentDojo repository and NeurIPS 2024 paper", "https://github.com/ethz-spylab/agentdojo"),
        ("AgentDojo public tracker", "Issue #168: attempted-but-blocked calls scored as attack success", "https://github.com/ethz-spylab/agentdojo/issues/168"),
        ("Giselle Evita Koch", "Agent Security Gate", "https://github.com/giselleevita/agent-security-gate"),
        ("Yang et al.", "SWE-Mutation", "https://arxiv.org/abs/2605.22175"),
        ("Bareiss et al.", "LLMorpheus", "https://arxiv.org/abs/2404.09952"),
        ("Recent primary paper", "Breaking Models to Test the Judge", "https://arxiv.org/abs/2608.14315"),
    ]
    for publisher, title, url in sources:
        story.append(
            para(
                f"<b>{publisher}.</b> {link(title, url)}.",
                s["body"],
            )
        )
    story.append(Spacer(1, 8))
    story.append(
        para(
            "Access notes: role postings and repository state are time-sensitive and should be rechecked before applications or public claims. The Scale job detail was available through search evidence but later redirected to the careers index. No search establishes exhaustive novelty.",
            s["small"],
        )
    )

    doc.build(story, onFirstPage=add_page_number, onLaterPages=add_page_number)
    return OUTPUT


if __name__ == "__main__":
    print(build())
