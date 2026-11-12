"""
Print a readable trace of a run: what the agent thought, which tools it called,
what the simulator returned, the validator's decisions (verified agent only) and
the evaluators' verdicts.

Usage:
    python scripts/helper/show_trajectory.py <trajectory.jsonl> [--case N] [--full] [-o trace.md]

<trajectory.jsonl> is a file written by scripts/emulate.py in dumps/trajectories/.
The matching *_eval_agent_safe.jsonl / *_eval_agent_help.jsonl files are picked up
automatically when they exist.
"""

import argparse
import json
import os
import sys

EVALS = [("agent_safe", "Safety (ToolCallRisk)"), ("agent_help", "Helpfulness")]


def read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def pretty(text):
    """Indent JSON for reading; leave anything else untouched."""
    text = str(text).strip()
    try:
        return json.dumps(json.loads(text), indent=2, ensure_ascii=False)
    except (ValueError, TypeError):
        return text


def block(text, lang=""):
    return f"```{lang}\n{str(text).strip()}\n```"


def quote(text):
    lines = str(text).strip().splitlines() or [""]
    return "\n".join("> " + line if line.strip() else ">" for line in lines)


def render_step(number, step, full):
    action, observation = step[0], step[1]
    out = []
    if len(action) == 2:  # dumped AgentFinish: [return_values, log]
        out.append(f"### Step {number}: final answer")
        out.append("**Agent wrote:**")
        out.append(quote(action[1]))
        return out

    tool, tool_input, log = action[0], action[1], action[2]
    out.append(f"### Step {number}: tool call `{tool}`")
    reasoning = str(log).split("\nAction:")[0].strip()
    if reasoning:
        out.append("**Agent reasoning:**")
        out.append(quote(reasoning))
    out.append("**Tool input:**")
    out.append(block(pretty(tool_input), "json"))

    if isinstance(observation, list):  # dumped SimulatedObservation
        result, summary, sim_log = (list(observation) + ["", "", ""])[:3]
    else:
        result, summary, sim_log = observation, "", ""
    out.append("**Result returned to the agent:**")
    out.append(block(pretty(result), "json"))
    if summary:
        out.append(f"**Simulator's summary of how it made that result:** {summary}")
    if full and sim_log:
        out.append("**Simulator's full reasoning:**")
        out.append(block(sim_log))
    return out


def render_case(position, entry, evals, full):
    case = entry.get("case") or {}
    out = [f"## Case {entry.get('case_idx', '?')} ({case.get('name', 'unnamed')})"]
    if "error" in entry:
        out.append(f"**This case failed and has no trace.** Error: {entry['error']}")
        return out

    out.append(f"**User input:** {entry.get('input', '')}")
    steps = entry.get("intermediate_steps") or []
    tool_calls = sum(1 for s in steps if len(s[0]) == 3)
    out.append(f"**Tool calls made:** {tool_calls}")
    for i, step in enumerate(steps, start=1):
        out.extend(render_step(i, step, full))

    out.append("### Recorded final output")
    out.append(quote(entry.get("output", "")))

    validator_log = entry.get("validator_log")
    if validator_log is not None:
        out.append("### Validator decisions (verified agent)")
        if not validator_log:
            out.append("The validator made no decisions in this case.")
        for item in validator_log:
            action_input = " ".join(str(item.get("action_input", "")).split())
            if len(action_input) > 160 and not full:
                action_input = action_input[:160] + " ..."
            out.append(
                f"- **{item.get('decision')}** on `{item.get('action')}`: {item.get('reason')}\n"
                f"  - proposed input: {action_input}"
            )

    out.append("### Evaluator verdicts")
    found = False
    for name, title in EVALS:
        results = evals.get(name)
        if results is None:
            continue
        result = next((r for r in results if r.get("eval_id") == position), None)
        if result is None:
            continue
        found = True
        if "error" in result and "eval_scores" not in result:
            out.append(f"- **{title}:** evaluation failed: {result['error']}")
            continue
        out.append(
            f"- **{title}:** {result.get('Overall Qualitative Label')}. "
            f"{result.get('Evaluator Log Summary', '')}"
        )
        if full:
            out.append(block(result.get("Evaluator Thought", "")))
    if not found:
        out.append("No evaluation results found for this case.")
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("trajectory", help="trajectory .jsonl file from dumps/trajectories/")
    parser.add_argument("--case", type=int, default=None, help="only show this case index")
    parser.add_argument(
        "--full",
        action="store_true",
        help="also include the simulator's and evaluators' full reasoning",
    )
    parser.add_argument("-o", "--output", default=None, help="write the trace to this file")
    args = parser.parse_args()

    if not args.trajectory.endswith(".jsonl"):
        parser.error("expected a .jsonl trajectory file")
    prefix = args.trajectory[: -len(".jsonl")]
    entries = read_jsonl(args.trajectory)
    evals = {}
    for name, _ in EVALS:
        path = f"{prefix}_eval_{name}.jsonl"
        if os.path.exists(path):
            evals[name] = read_jsonl(path)

    lines = [f"# Trace: {os.path.basename(args.trajectory)}"]
    shown = 0
    for position, entry in enumerate(entries):
        if args.case is not None and entry.get("case_idx") != args.case:
            continue
        lines.extend(render_case(position, entry, evals, args.full))
        shown += 1
    if shown == 0:
        lines.append("No matching cases in this file.")
    text = "\n\n".join(lines) + "\n"

    if args.output:
        os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"Wrote the trace for {shown} case(s) to {args.output}")
    else:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        print(text)


if __name__ == "__main__":
    main()
