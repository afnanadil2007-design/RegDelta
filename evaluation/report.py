"""Render evaluation results as Markdown tables, from the result files only.

No number in the generated page is typed by hand: every cell comes from a
``summary.json`` written by ``run_eval``. Rerun this after any new run.

    python -m evaluation.report                      # newest sample run (+ full-fast if present)
    python -m evaluation.report --label 2026-10-15-ablation
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from evaluation.run_eval import RESULTS_DIR

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "docs" / "evaluation-results.md"
MODE_LABEL = {
    "dense": "Dense",
    "lexical": "Lexical",
    "hybrid": "Hybrid (RRF)",
    "hybrid_rerank": "Hybrid + rerank",
}


def _metric(block: dict[str, Any], name: str, subset: str) -> dict[str, Any] | None:
    return next((m for m in block["metrics"] if m["name"] == name and m["subset"] == subset), None)


def _value(block: dict[str, Any], name: str, subset: str, *, ci: bool = False) -> str:
    metric = _metric(block, name, subset)
    if metric is None:
        return "—"
    if name.endswith("_ms"):
        return f"{metric['value']:,.0f}"
    text = f"{metric['value']:.3f}"
    if ci and metric.get("ci"):
        low, high = metric["ci"]
        text += f" ({low:.2f}–{high:.2f})"
    return text


def _refusal(block: dict[str, Any], subset: str) -> str:
    metric = _metric(block, "refusal_rate", subset)
    if metric is None:
        return "—"
    if metric.get("note", "").startswith("This mode has no refusal"):
        return "never refuses"
    refused = round(metric["value"] * metric["n"])
    text = f"{refused} of {metric['n']}"
    if metric.get("ci"):
        low, high = metric["ci"]
        text += f" ({low:.2f}–{high:.2f})"
    return text


def _provenance(prov: dict[str, Any]) -> list[str]:
    code = prov["code"]
    identity = f"`{code['git_sha'][:12]}`"
    if code["dirty"]:
        identity += f" with uncommitted changes, digest `{code['dirty_digest'][:16]}`"
    else:
        identity += " (evaluated sources clean)"
    if code.get("recorded"):
        identity += f", recorded {code['recorded']}"
    models = prov["models"]
    machine = prov["machine"]
    data = prov["data"]
    config = prov["retrieval_config"]
    timing = prov["timing"]
    loads = ", ".join(
        f"{key.replace('_', ' ')} {value}" for key, value in timing.items() if key != "method"
    )
    queries = data["queries"]
    resummarised = prov.get("resummarised")
    return [
        f"- Code: {identity}",
        f"- Generated: {prov['generated']}",
        f"- Embedding model: `{models['embedding']['id']}` @ "
        f"`{(models['embedding']['revision'] or 'unknown')[:12]}`",
        f"- Reranker: `{models['reranker']['id']}` @ "
        f"`{(models['reranker']['revision'] or 'unknown')[:12]}`, "
        f"{models['reranker']['activation']}",
        f"- Retrieval: RRF k={config['rrf_k']}, {config['retrieve_top_n']} candidates per "
        f"retriever, refusal threshold {config['relevance_threshold']} "
        f"({config['threshold_origin']})",
        f"- Data: {data['corpus']}; gold `{data['gold_file']}` "
        f"(sha256 `{data['gold_sha256'][:12]}`)"
        + (
            f"; sample `{data['sample_manifest']}` (seed {data['sample_seed']})"
            if data.get("sample_manifest")
            else "; every gold query"
        ),
        f"- Queries: {queries['semantic']} semantic, {queries['identifier']} identifier, "
        f"{queries['out_of_scope']} out-of-scope to refuse, "
        f"{queries.get('control', 0)} answerable controls without a relevance label",
        f"- Relevance: {data['relevance']}; {data['exclusions']}",
        f"- Machine: {machine['cpu']}, {machine['logical_cpus']} logical CPUs, "
        f"{machine['memory_gib']} GiB RAM, torch {machine.get('torch')} "
        f"({machine.get('torch_threads')} threads), sentence-transformers "
        f"{machine.get('sentence_transformers')}, {machine['os']}",
        f"- Timing: {timing['method']}. Seconds: {loads}.",
        *(
            [
                f"- Summary recomputed {resummarised['generated']} by "
                f"`{resummarised['code']['git_sha'][:12]}`"
                + (" with uncommitted changes" if resummarised["code"]["dirty"] else "")
                + f": {resummarised['method']}"
            ]
            if resummarised
            else []
        ),
    ]


def render_sample(summary: dict[str, Any], label: str) -> list[str]:
    modes = summary["modes"]
    lines = [
        f"## Four modes, one query manifest (`{label}`)",
        "",
        *_provenance(summary["provenance"]),
        "",
        "Ranking quality is measured with the refusal threshold not applied, so every "
        "mode is scored on the same ranked lists. Intervals are 95% cluster-bootstrap "
        "intervals that resample citing circulars (queries from one circular move "
        "together); out-of-scope refusal uses the Wilson interval.",
        "",
        "| Mode | Recall@1 | Recall@5 | Recall@10 | MRR@10 | p50 ms | p95 ms |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for mode, block in modes.items():
        lines.append(
            f"| {MODE_LABEL.get(mode, mode)} | {_value(block, 'recall@1', 'all')} | "
            f"{_value(block, 'recall@5', 'all')} | {_value(block, 'recall@10', 'all', ci=True)} | "
            f"{_value(block, 'mrr@10', 'all', ci=True)} | "
            f"{_value(block, 'latency_p50_ms', 'all')} | {_value(block, 'latency_p95_ms', 'all')} |"
        )
    first = next(iter(modes.values()))
    n_in, n_out = first["n_in_scope"], first["n_out_of_scope"]
    n_control = first.get("n_controls", 0)
    lines += [
        "",
        f"Denominator: {n_in} labelled in-scope queries per mode. Latency also includes the "
        f"{n_out} questions to refuse and the {n_control} controls.",
        "",
        "### Refusal and coverage",
        "",
        "Only the reranked mode has a refusal threshold. Controls are on-topic questions the "
        "corpus can answer but that have no relevance label, so they count only here.",
        "",
        "| Mode | Refused, labelled in scope (unwanted) | Refused, controls (unwanted) | "
        "Refused, out of scope (wanted) | Recall@10 counting refusals as misses |",
        "|---|---:|---:|---:|---:|",
    ]
    for mode, block in modes.items():
        lines.append(
            f"| {MODE_LABEL.get(mode, mode)} | {_refusal(block, 'in_scope')} | "
            f"{_refusal(block, 'control')} | {_refusal(block, 'out_of_scope')} | "
            f"{_value(block, 'answered_recall@10', 'in_scope', ci=True)} |"
        )
    lines += [
        "",
        "### By query type",
        "",
        "| Mode | Semantic Recall@10 | Semantic MRR@10 | Identifier Recall@10 | "
        "Identifier MRR@10 |",
        "|---|---:|---:|---:|---:|",
    ]
    for mode, block in modes.items():
        lines.append(
            f"| {MODE_LABEL.get(mode, mode)} | {_value(block, 'recall@10', 'semantic', ci=True)} | "
            f"{_value(block, 'mrr@10', 'semantic')} | "
            f"{_value(block, 'recall@10', 'identifier', ci=True)} | "
            f"{_value(block, 'mrr@10', 'identifier')} |"
        )
    if summary.get("paired_differences"):
        lines += [
            "",
            "### Paired differences (same queries)",
            "",
            "| A − B | Metric | Difference | 95% interval |",
            "|---|---|---:|---|",
        ]
        for d in summary["paired_differences"]:
            interval = f"{d['ci'][0]:+.3f} to {d['ci'][1]:+.3f}" if d["ci"] else "too few clusters"
            lines.append(
                f"| {MODE_LABEL.get(d['a'], d['a'])} − {MODE_LABEL.get(d['b'], d['b'])} | "
                f"{d['metric']} | {d['difference']:+.3f} | {interval} |"
            )
    lines += ["", "### Misses (first six per mode, by query id)", ""]
    for mode, block in modes.items():
        examples = block["error_examples"]
        if not examples:
            lines.append(f"- {MODE_LABEL.get(mode, mode)}: none")
            continue
        lines.append(f"- {MODE_LABEL.get(mode, mode)}:")
        for e in examples:
            lines.append(
                f"  - `{e['query_id']}` ({e['subset']}): wanted {', '.join(e['relevant'])}; "
                f"got {', '.join(e['top3']) or 'nothing'}"
            )
    return lines


def render_full(summary: dict[str, Any], label: str) -> list[str]:
    modes = summary["modes"]
    lines = [
        "",
        f"## Fast modes over every gold query (`{label}`)",
        "",
        *_provenance(summary["provenance"]),
        "",
        "| Mode | Queries | Recall@10 | MRR@10 | Semantic Recall@10 | Identifier Recall@10 | "
        "p50 ms |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for mode, block in modes.items():
        lines.append(
            f"| {MODE_LABEL.get(mode, mode)} | {block['n_in_scope']} | "
            f"{_value(block, 'recall@10', 'all', ci=True)} | "
            f"{_value(block, 'mrr@10', 'all', ci=True)} | "
            f"{_value(block, 'recall@10', 'semantic')} | "
            f"{_value(block, 'recall@10', 'identifier')} | "
            f"{_value(block, 'latency_p50_ms', 'all')} |"
        )
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render evaluation results as Markdown.")
    parser.add_argument("--label", default=None, help="sample run label (default: newest)")
    parser.add_argument("--full-label", default="full-fast")
    args = parser.parse_args(argv)

    runs = sorted(
        (p for p in RESULTS_DIR.glob("*/summary.json") if p.parent.name != args.full_label),
        key=lambda p: p.stat().st_mtime,
    )
    sample = (
        RESULTS_DIR / args.label / "summary.json" if args.label else (runs[-1] if runs else None)
    )
    if sample is None or not sample.is_file():
        print("No sample run found; run python -m evaluation.run_eval first.")
        return 1
    lines = [
        "# Evaluation results",
        "",
        "Generated by `python -m evaluation.report` from the files under "
        "`evaluation/results/retrieval/`; do not edit by hand. Method and limits: "
        "[evaluation.md](evaluation.md).",
        "",
    ]
    lines += render_sample(json.loads(sample.read_text()), sample.parent.name)
    full = RESULTS_DIR / args.full_label / "summary.json"
    if full.is_file():
        lines += render_full(json.loads(full.read_text()), args.full_label)
    OUTPUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
