"""Action validator using Prolog formalization with precondition-chain resolution."""
from typing import Tuple, List, Set, Optional
from dotenv import load_dotenv
from toolemu.formalization.violation_states import APPROVED, REVISION_REQUIRED, REJECT_REQUEST, ACTION_REJECTED, ViolationDetectionState, APPROVED_WITH_CONSTRAINTS
from toolemu.utils.io import (
    read_and_execute_prolog_program,
    parse_last_step_postcondition_output,
    parse_postcondition_action_candidates_output,
    parse_risky_actions_output,
    parse_all_steps_for_action_output,
    StepInfo,
)

DEBUG = False

load_dotenv()

def _debug(label: str, value):
    """Print debug info if DEBUG is enabled."""
    if DEBUG:
        print(f"\n[DEBUG] {label}:")
        print(f"        {value}")

def quote_prolog_atom(atom: str) -> str:
    """Quote a Prolog atom if it contains spaces or special characters."""
    if ' ' in atom or '\t' in atom or '\n' in atom or '"' in atom or "'" in atom:
        escaped = atom.replace("'", "\\'")
        return f"'{escaped}'"
    return atom


def _is_repeatable_template_step(step: StepInfo) -> bool:
    """Return True when a step's command parameter is a placeholder template."""
    params_lower = step.params.lower()
    return (
        step.constraint.lower() != "none"
        and "param(command" in params_lower
        and "<" in step.params
        and ">" in step.params
    )


def get_candidate_actions_for_postcondition(case_idx: int, postcondition: str) -> List[str]:
    query_candidates = (
        "get_action_param_candidates_for_postcondition("
        f"{quote_prolog_atom(postcondition.lower())}, CandidateList)"
    )
    success_candidates, output_candidates = read_and_execute_prolog_program(case_idx, query_candidates)
    candidate_actions: List[str] = []
    if success_candidates:
        try:
            candidate_actions = parse_postcondition_action_candidates_output(output_candidates).candidates
        except ValueError:
            candidate_actions = []
    return [
        c for c in candidate_actions
        if c.lower() not in {"none", "candidate(final answer,[])"}
    ]


def validate_action(
    case_idx: int,
    action_name: str,
    action_input: str,
    satisfied_postconditions: Optional[Set[str]] = None,
    approved_step_numbers: Optional[Set[int]] = None,
) -> Tuple[bool, str, ViolationDetectionState, Optional[StepInfo]]:

    if satisfied_postconditions is None:
        satisfied_postconditions = set()
    if approved_step_numbers is None:
        approved_step_numbers = set()

    if DEBUG:
        print("\n" + "="*60)
        print("VALIDATE_ACTION CALLED")
        print("="*60)
        _debug("case_idx", case_idx)
        _debug("action_name", action_name)
        _debug("action_input", action_input[:200] + "..." if len(action_input) > 200 else action_input)
        _debug("satisfied_postconditions", satisfied_postconditions if satisfied_postconditions else "(empty)")
        _debug("approved_step_numbers", sorted(approved_step_numbers) if approved_step_numbers else "(empty)")

    # Normalize action name to lowercase for Prolog
    action_lower = action_name.lower()
    action_input_lower = action_input.lower()

    # -------------------------------------------------------------------------
    # EARLY CHECK: Final Answer — verify last step's postcondition is satisfied
    # -------------------------------------------------------------------------
    if action_lower == "final answer":
        _debug("Final Answer detected", "Checking if last step postcondition is satisfied")

        query_last = "get_last_step_postcondition(PostList)"
        success_last, output_last = read_and_execute_prolog_program(case_idx, query_last)

        if success_last:
            try:
                last_post = parse_last_step_postcondition_output(output_last).postconditions
                _debug("last step postconditions (parsed)", last_post)
            except ValueError:
                last_post = []

            if last_post:
                last_postcondition = last_post[0].lower()
                if last_postcondition not in satisfied_postconditions:
                    candidate_actions = get_candidate_actions_for_postcondition(case_idx, last_postcondition)
                    candidate_preview = ", ".join(candidate_actions[:3])
                    _debug("RETURNING", f"REVISION_REQUIRED (last step postcondition '{last_postcondition}' not satisfied)")
                    return (
                        False,
                        f"Postcondition '{last_postcondition}' has not been satisfied. "
                        f"Execute one of these actions first: "
                        f"{candidate_preview if candidate_preview else 'a tool that achieves this postcondition.'}",
                        REVISION_REQUIRED,
                        None,
                    )

        _debug("RETURNING", "APPROVED (Final Answer — all steps completed)")
        return True, f"Action 'Final Answer' is approved", APPROVED, None

    action_quoted = quote_prolog_atom(action_lower)
    # _debug("action_quoted (for Prolog)", action_quoted)

    # -------------------------------------------------------------------------
    # EARLY CHECK: risky_action pattern matching against actual runtime input
    # -------------------------------------------------------------------------
    risky_user_consent_pattern = None  # set if a user_consent match is found
    risky_repeat_consent_pattern = None  # set if a repeat_consent match is found

    query_risky = f"get_risky_actions({action_quoted}, PatternList)"
    success_risky, output_risky = read_and_execute_prolog_program(case_idx, query_risky)

    if success_risky:
        try:
            risky_resp = parse_risky_actions_output(output_risky)
            _debug("risky_action entries", [(e.pattern, e.disposition) for e in risky_resp.entries])

            # Check patterns longest-first so more specific patterns take priority
            sorted_entries = sorted(risky_resp.entries, key=lambda e: len(e.pattern), reverse=True)
            for entry in sorted_entries:
                if entry.pattern.lower() in action_input_lower:
                    if entry.disposition == "reject":
                        _debug("RETURNING", f"REJECT_REQUEST (matched risky pattern '{entry.pattern}' → reject)")
                        return (
                            False,
                            f"Action '{action_name}' blocked: input contains "
                            f"dangerous pattern '{entry.pattern}'. This action is "
                            f"unconditionally rejected by safety policy.",
                            ACTION_REJECTED,
                            None,
                        )
                    elif entry.disposition == "user_consent":
                        risky_user_consent_pattern = entry.pattern
                        _debug("risky_action match", f"pattern '{entry.pattern}' → user_consent (will enforce after postcondition inference)")
                        break
                    elif entry.disposition == "repeat_consent":
                        risky_repeat_consent_pattern = entry.pattern
                        _debug("risky_action match", f"pattern '{entry.pattern}' → repeat_consent (will enforce for every matching action)")
                        break
        except ValueError:
            _debug("risky_action parse", "no risky_action facts or parse error (non-fatal)")
    else:
        _debug("risky_action query", "query failed or no risky_action facts defined (non-fatal)")

    # -------------------------------------------------------------------------
    # CHAIN RESOLUTION: Find the current step via precondition/postcondition chain
    # -------------------------------------------------------------------------
    query_steps = f"get_all_steps_for_action({action_quoted}, StepList)"
    success_steps, output_steps = read_and_execute_prolog_program(case_idx, query_steps)

    if not success_steps:
        _debug("RETURNING", "APPROVED (action not in refined plan — no restriction)")
        return True, f"Action '{action_name}' is approved (not in refined plan)", APPROVED, None

    try:
        all_steps = parse_all_steps_for_action_output(output_steps).steps
    except ValueError:
        _debug("RETURNING", "APPROVED (step parse error — no restriction)")
        return True, f"Action '{action_name}' is approved (parse error)", APPROVED, None

    if not all_steps:
        _debug("RETURNING", "APPROVED (no refined_steps for this action)")
        return True, f"Action '{action_name}' is approved (no refined_steps)", APPROVED, None

    _debug("all_steps_for_action", [(s.step_num, s.precondition, s.postcondition, s.constraint) for s in all_steps])

    ready_steps: List[StepInfo] = []
    blocked_steps: List[StepInfo] = []

    for step in all_steps:
        post_done = step.step_num in approved_step_numbers and not _is_repeatable_template_step(step)
        pre_ok = (step.precondition.lower() == "true"
                  or step.precondition.lower() in satisfied_postconditions)

        if post_done:
            continue
        if pre_ok:
            ready_steps.append(step)
        else:
            blocked_steps.append(step)

    _debug("ready_steps", [s.step_num for s in ready_steps] if ready_steps else "(none)")
    _debug("blocked_steps", [s.step_num for s in blocked_steps] if blocked_steps else "(none)")

    # All steps for this action are already completed
    if not ready_steps and not blocked_steps:
        _debug("RETURNING", "APPROVED (all steps for this action already completed)")
        return True, f"Action '{action_name}' is approved", APPROVED, None

    # No ready steps — preconditions not met
    if not ready_steps:
        blocked_steps.sort(key=lambda s: s.step_num)
        unmet_pre = blocked_steps[0].precondition
        candidate_actions = get_candidate_actions_for_postcondition(case_idx, unmet_pre)
        candidate_preview = ", ".join(candidate_actions[:3])
        _debug("RETURNING", f"REVISION_REQUIRED (unmet precondition: {unmet_pre})")
        return (
            False,
            f"Unmet precondition: '{unmet_pre}'. "
            f"Execute an action that satisfies this first"
            f"{f' (candidates: {candidate_preview})' if candidate_preview else ''}.",
            REVISION_REQUIRED,
            None,
        )

    # Pick the ready step with the lowest step number
    ready_steps.sort(key=lambda s: s.step_num)
    current_step = ready_steps[0]

    _debug("current_step", f"step {current_step.step_num}")
    _debug("postcondition", current_step.postcondition)

    # -------------------------------------------------------------------------
    # Check for step-specific constraints and risky_action patterns
    # -------------------------------------------------------------------------
    has_step_constraint = current_step.constraint.lower() != "none"
    _debug("constraint", current_step.constraint)

    if has_step_constraint or risky_user_consent_pattern or risky_repeat_consent_pattern:
        reasons = []
        if has_step_constraint:
            reasons.append(current_step.constraint)
        if risky_user_consent_pattern:
            reasons.append(f"risky pattern '{risky_user_consent_pattern}' detected in input")
        if risky_repeat_consent_pattern:
            reasons.append(
                f"repeat confirmation required for matching risky pattern "
                f"'{risky_repeat_consent_pattern}'"
            )
        constraint_desc = '; '.join(reasons)
        _debug("RETURNING", f"APPROVED_WITH_CONSTRAINTS (reasons: {constraint_desc})")
        return False, f"Action '{action_name}' requires user consent: {constraint_desc}. Please confirm with the user before proceeding.", APPROVED_WITH_CONSTRAINTS, current_step

    _debug("RETURNING", f"APPROVED (step_num={current_step.step_num}, postcondition={current_step.postcondition})")
    return True, f"Action '{action_name}' is approved", APPROVED, current_step
