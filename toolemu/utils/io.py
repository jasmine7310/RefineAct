import json
import os
import os.path as osp
import re
from typing import Tuple, List, TypeVar, Type

import pandas as pd

from .my_typing import *

# ---------------------------------------------------------------------------
# Optional dependency: pydantic
# ---------------------------------------------------------------------------
try:
    from pydantic import BaseModel  # type: ignore[import]
except ImportError as exc:  # pragma: no cover
    class BaseModel:  # type: ignore[override]
        def __init__(self, *_, **__):
            raise ImportError(
                "pydantic is required for parsing Prolog predicate responses. "
                "Install it with `pip install pydantic`."
            ) from exc

        def model_dump(self, *_, **__):
            raise ImportError(
                "pydantic is required for parsing Prolog predicate responses. "
                "Install it with `pip install pydantic`."
            ) from exc

        def dict(self, *_, **__):
            raise ImportError(
                "pydantic is required for parsing Prolog predicate responses. "
                "Install it with `pip install pydantic`."
            ) from exc

PredicateListModel = TypeVar("PredicateListModel", bound=BaseModel)
DEFAULT_FORMAL_CASES_PATH = "assets/five_test_cases_formal.json"
FORMAL_CASES_PATH = DEFAULT_FORMAL_CASES_PATH


def set_formal_cases_path(path: str) -> None:
    """Set the active formalized cases file used by the validator."""
    global FORMAL_CASES_PATH
    FORMAL_CASES_PATH = path


def create_folder(file_path: str) -> bool:
    """Create folders for the file_path if the folders do not exist.

    Args:
        file_path (str): The path to the file.

    Returns:
        bool: True if the folder is created, False if the folder already exists.
    """
    folder_path = osp.dirname(file_path)
    if not osp.exists(file_path):
        os.makedirs(folder_path, exist_ok=True)
        return True
    return False


def remove_file(file_path: str) -> None:
    """Remove a file."""
    if osp.exists(file_path):
        os.remove(file_path)


def append_file(
    file_path: str,
    text: str,
    mode: str = "a",
    seperator: str = "\n\n########################\n",
) -> None:
    """Append text to a file."""
    if create_folder(file_path):
        mode = "w"
    with open(file_path, mode=mode) as f:
        f.write(seperator)
        f.write(text)


def append_jsonl(
    file_path: str,
    content: Any,
    mode: str = "a",
) -> None:
    """Append a json object to a jsonl file."""
    if create_folder(file_path):
        mode = "w"
    with open(file_path, mode=mode) as f:
        f.write(json.dumps(content) + "\n")


def write_json(content: Any, file_path: str, indent=4) -> None:
    """Write a json object to a json file."""
    create_folder(file_path)
    with open(file_path, "w") as f:
        json.dump(content, f, indent=indent)


def read_json(file_path: str) -> Any:
    with open(file_path, "r") as f:
        return json.load(f)


def read_jsonl(file_path: str) -> List[Any]:
    all_data = []
    with open(file_path, "r") as f:
        for line in f:
            line = line.strip()
            if line:
                data = json.loads(line)
                all_data.append(data)
    return all_data


def read_file(file_path: str) -> Any:
    suffix = file_path.split(".")[-1]
    if suffix == "json":
        return read_json(file_path)
    elif suffix == "jsonl":
        return read_jsonl(file_path)
    elif suffix in ["txt", "log", "md"]:
        with open(file_path, "r") as f:
            return f.readlines()
    elif suffix in ["csv"]:
        return pd.read_csv(file_path)
    else:
        raise ValueError(f"Unknown file type: {suffix}")


def remove_file_extension(file_path: str) -> str:
    """Remove the file extension suffix of a file path."""
    return ".".join(file_path.split(".")[:-1])


def replace_file_extension(file_path: str, new_extension: str) -> str:
    """Replace the file extension suffix of a file path."""
    return remove_file_extension(file_path) + f".{new_extension}"


def get_prolog_program(json_path: str, case_name: str) -> Optional[str]:
    """
    Get the Prolog program for a specific test case by name.

    Args:
        json_path: Path to JSON file containing test cases
        case_name: Name of the test case (e.g., "official_2")

    Returns:
        The Prolog program string, or None if case not found or has no program

    Example:
        >>> prolog = get_prolog_program('assets/five_test_cases.json', 'official_2')
        >>> print(prolog)
    """
    test_cases = read_json(json_path)

    for case in test_cases:
        if case.get('name') == case_name:
            return case.get('prolog_program')

    return None


def read_and_execute_prolog_program(case_idx: int, query: str) -> Tuple[bool, str]:
    """
    Read the Prolog program for a specific test case by index and execute a query.

    Args:
        case_idx: Index of the test case in the formalized_cases.json array
        query: The Prolog query to execute

    Returns:
        Tuple of (is_valid: bool, output: str) where is_valid indicates if the query
        executed successfully and output contains the results or error message

    Example:
        >>> is_valid, output = read_and_execute_prolog_program(0, "find_temporal_rules_with_extra_args(VAR)")
        >>> print(f"Valid: {is_valid}")
        >>> print(f"Output: {output}")
    """
    from toolemu.formalization.validator import execute_prolog_query

    test_cases = read_json(FORMAL_CASES_PATH)

    if case_idx >= len(test_cases) or case_idx < 0:
        return (
            False,
            f"Case index {case_idx} out of range for '{FORMAL_CASES_PATH}'. "
            f"Valid range: 0-{len(test_cases)-1}",
        )

    case = test_cases[case_idx]
    prolog_program = case.get('prolog_program')

    if not prolog_program:
        return False, f"No prolog program found for case at index {case_idx}"

    additional_rule = """
    :- dynamic risky_action/3.

    implied_risky_action(Action, Prefix, repeat_consent) :-
        refined_step(_, Action, Params, _, _, constraint(_, _)),
        member(param(command, Template), Params),
        sub_atom(Template, Before, _, _, '<'),
        sub_atom(Template, _, _, _, '>'),
        sub_atom(Template, 0, Before, _, Prefix),
        Prefix \\= ''.

    get_step_preconditions(Action, Params, PreList) :-
        findall(Pre, refined_step(_, Action, Params, Pre, _, _), Found),
        ( Found = [] -> PreList = [none] ; PreList = Found ).

    get_step_postconditions(Action, PostList) :-
        findall(Post, refined_step(_, Action, _, _, Post, _), Found),
        ( Found = [] -> PostList = [none] ; PostList = Found ).

    get_step_postconditions(Action, Precondition, PostList) :-
        findall(Post, refined_step(_, Action, _, Precondition, Post, _), Found),
        ( Found = [] -> PostList = [none] ; PostList = Found ).

    get_action_step_numbers(Action, Params, StepList) :-
        findall(Step, refined_step(Step, Action, Params, _, _, _), Found),
        ( Found = [] -> StepList = [none] ; StepList = Found ).

    get_step_constraint(Action, Params, ConstraintList) :-
        findall(C, refined_step(_, Action, Params, _, _, C), Found),
        ( Found = [] -> ConstraintList = [none] ; ConstraintList = Found ).

    get_action_params(Action, ParamList) :-
        findall(Params, refined_step(_, Action, Params, _, _, _), Found),
        ( Found = [] -> ParamList = [none] ; ParamList = Found ).

    get_last_step_postcondition(PostList) :-
        findall(N, refined_step(N, _, _, _, _, _), Steps),
        max_list(Steps, MaxStep),
        findall(Post, refined_step(MaxStep, _, _, _, Post, _), PostList).

    get_action_param_candidates_for_postcondition(Postcondition, CandidateList) :-
        findall(candidate(Action, Params), refined_step(_, Action, Params, _, Postcondition, _), Found),
        ( Found = [] -> CandidateList = [none] ; sort(Found, CandidateList) ).

    get_risky_actions(Action, PatternList) :-
        findall(
            risky(Pattern, Disposition),
            (
                risky_action(Action, Pattern, Disposition)
                ;
                implied_risky_action(Action, Pattern, Disposition)
            ),
            Found
        ),
        ( Found = [] -> PatternList = [] ; sort(Found, PatternList) ).

    get_all_steps_for_action(Action, StepList) :-
        findall(step_info(N, Params, Pre, Post, Constraint),
                refined_step(N, Action, Params, Pre, Post, Constraint),
                Found),
        ( Found = [] -> StepList = [] ; StepList = Found ).
    """
    prolog_program = prolog_program + additional_rule

    is_valid, output = execute_prolog_query(prolog_program, query)
    return is_valid, output


# ---------------------------------------------------------------------------
# Prolog predicate parsing helpers
# ---------------------------------------------------------------------------

# Pattern for 2-arg predicates: predicate(action, [list])
# Use greedy .* and anchor to end ($) to handle nested brackets like cc([]), bcc([])
PROLOG_LIST_PATTERN_2ARG = r"{predicate}\((?P<action>[^,\[]+),\s*\[(?P<values>.*)\]\)\s*$"

# Pattern for 3-arg predicates: predicate(action, middle_arg, [list])
# middle_arg can have nested brackets like [to(x),cc([]),bcc([])]
# Use greedy .+ for middle (backtracks to find final ,[values]))
# values (step numbers, preconditions) are simple - no nested brackets
PROLOG_LIST_PATTERN_3ARG = r"{predicate}\((?P<action>[^,]+),\s*(?P<middle>.+),\s*\[(?P<values>[^\[\]]*)\]\)\s*$"


class StepPreconditionsResponse(BaseModel):
    predicate: str
    action: str
    preconditions: List[str]


class StepPostconditionsResponse(BaseModel):
    predicate: str
    action: str
    postconditions: List[str]


class ActionStepNumbersResponse(BaseModel):
    predicate: str
    action: str
    step_numbers: List[str]


class StepConstraintResponse(BaseModel):
    predicate: str
    action: str
    constraints: List[str]


class ActionParamsResponse(BaseModel):
    predicate: str
    action: str
    params: List[str]


class PostconditionActionCandidatesResponse(BaseModel):
    predicate: str
    action: str
    candidates: List[str]


def _split_prolog_list_items(raw_items: str) -> List[str]:
    raw_items = raw_items.strip()
    if not raw_items:
        return []

    items: List[str] = []
    buffer: List[str] = []
    paren_depth = 0
    bracket_depth = 0

    for char in raw_items:
        if char == ',' and paren_depth == 0 and bracket_depth == 0:
            item = ''.join(buffer).strip()
            if item:
                items.append(item)
            buffer = []
            continue

        if char == '(':
            paren_depth += 1
        elif char == ')':
            paren_depth = max(paren_depth - 1, 0)
        elif char == '[':
            bracket_depth += 1
        elif char == ']':
            bracket_depth = max(bracket_depth - 1, 0)

        buffer.append(char)

    tail = ''.join(buffer).strip()
    if tail:
        items.append(tail)

    return items


def _parse_prolog_predicate_list(
    output: str,
    predicate: str,
    num_args: int = 2,
) -> Tuple[str, List[str]]:
    """
    Parse Prolog predicate output.

    Args:
        output: Raw Prolog output string
        predicate: Name of the predicate
        num_args: Number of arguments (2 or 3). For 3-arg predicates like
                  get_action_step_numbers(action, params, [list]), the middle
                  arg is ignored and only action + list are returned.
    """
    if num_args == 3:
        pattern = PROLOG_LIST_PATTERN_3ARG.format(predicate=re.escape(predicate))
    else:
        pattern = PROLOG_LIST_PATTERN_2ARG.format(predicate=re.escape(predicate))

    match = re.search(pattern, output.strip(), flags=re.DOTALL)

    if not match:
        raise ValueError(f"Unexpected output for '{predicate}' (num_args={num_args}): {output}")

    action = match.group("action").strip()
    raw_items = match.group("values").strip()
    items = _split_prolog_list_items(raw_items)
    return action, items


def _build_response(
    output: str,
    predicate: str,
    model: Type[PredicateListModel],
    payload_key: str,
    num_args: int = 2,
) -> PredicateListModel:
    action, items = _parse_prolog_predicate_list(output, predicate, num_args)
    data = {"predicate": predicate, "action": action, payload_key: items}
    return model(**data)


def parse_step_preconditions_output(output: str) -> StepPreconditionsResponse:
    # 3-arg: get_step_preconditions(Action, Params, PreList)
    return _build_response(
        output=output,
        predicate="get_step_preconditions",
        model=StepPreconditionsResponse,
        payload_key="preconditions",
        num_args=3,
    )


def parse_step_postconditions_output(output: str) -> StepPostconditionsResponse:
    # 3-arg: get_step_postconditions(Action, Precondition, PostList)
    return _build_response(
        output=output,
        predicate="get_step_postconditions",
        model=StepPostconditionsResponse,
        payload_key="postconditions",
        num_args=3,
    )


def parse_action_step_numbers_output(output: str) -> ActionStepNumbersResponse:
    # 3-arg: get_action_step_numbers(Action, Params, StepList)
    return _build_response(
        output=output,
        predicate="get_action_step_numbers",
        model=ActionStepNumbersResponse,
        payload_key="step_numbers",
        num_args=3,
    )


def parse_step_constraint_output(output: str) -> StepConstraintResponse:
    # 3-arg: get_step_constraint(Action, Params, ConstraintList)
    return _build_response(
        output=output,
        predicate="get_step_constraint",
        model=StepConstraintResponse,
        payload_key="constraints",
        num_args=3,
    )


def parse_action_params_output(output: str) -> ActionParamsResponse:
    return _build_response(
        output=output,
        predicate="get_action_params",
        model=ActionParamsResponse,
        payload_key="params",
    )


def parse_postcondition_action_candidates_output(output: str) -> PostconditionActionCandidatesResponse:
    return _build_response(
        output=output,
        predicate="get_action_param_candidates_for_postcondition",
        model=PostconditionActionCandidatesResponse,
        payload_key="candidates",
    )


class LastStepPostconditionResponse(BaseModel):
    predicate: str
    postconditions: List[str]


def parse_last_step_postcondition_output(output: str) -> LastStepPostconditionResponse:
    """Parse output of get_last_step_postcondition(PostList) — a 1-arg predicate."""
    match = re.search(
        r'get_last_step_postcondition\(\[(?P<values>[^\]]*)\]\)',
        output.strip(),
    )
    if not match:
        raise ValueError(f"Unexpected output for 'get_last_step_postcondition': {output}")
    raw = match.group("values").strip()
    items = _split_prolog_list_items(raw) if raw else []
    return LastStepPostconditionResponse(
        predicate="get_last_step_postcondition",
        postconditions=items,
    )


class RiskyActionEntry(BaseModel):
    pattern: str
    disposition: str  # "reject", "user_consent", or "repeat_consent"


class RiskyActionsResponse(BaseModel):
    predicate: str
    action: str
    entries: List[RiskyActionEntry]


def parse_risky_actions_output(output: str) -> RiskyActionsResponse:
    """Parse output of get_risky_actions(Action, PatternList).

    Prolog output looks like:
      get_risky_actions(terminalexecute,[risky('rm -rf /',reject),risky('rm -rf',user_consent)])
    or an empty list [] when no risky_action facts match.
    """
    match = re.search(
        r"get_risky_actions\((?P<action>[^,]+),\s*\[(?P<values>.*)\]\)\s*$",
        output.strip(),
        flags=re.DOTALL,
    )
    if not match:
        raise ValueError(f"Unexpected output for 'get_risky_actions': {output}")

    action = match.group("action").strip()
    raw = match.group("values").strip()

    entries: List[RiskyActionEntry] = []
    if raw:
        items = _split_prolog_list_items(raw)
        for item in items:
            m = re.match(r"risky\((?P<pattern>.+),\s*(?P<disp>\w+)\)", item.strip())
            if m:
                pattern = m.group("pattern").strip().strip("'")
                disposition = m.group("disp").strip()
                entries.append(RiskyActionEntry(pattern=pattern, disposition=disposition))

    return RiskyActionsResponse(predicate="get_risky_actions", action=action, entries=entries)


# ---------------------------------------------------------------------------
# get_all_steps_for_action parser
# ---------------------------------------------------------------------------

class StepInfo(BaseModel):
    step_num: int
    action: str
    params: str
    precondition: str
    postcondition: str
    constraint: str


class AllStepsForActionResponse(BaseModel):
    predicate: str
    action: str
    steps: List[StepInfo]


def parse_all_steps_for_action_output(output: str) -> AllStepsForActionResponse:
    """Parse output of get_all_steps_for_action(Action, StepList).

    Prolog output looks like:
      get_all_steps_for_action(terminalexecute,[step_info(1,[param(...)],pre,post,constraint),...])
    """
    action, raw_items = _parse_prolog_predicate_list(
        output, "get_all_steps_for_action", num_args=2
    )

    steps: List[StepInfo] = []
    for item in raw_items:
        item = item.strip()
        if not item.startswith("step_info("):
            continue
        inner = item[len("step_info("):]
        if inner.endswith(")"):
            inner = inner[:-1]
        args = _split_prolog_list_items(inner)
        if len(args) >= 5:
            steps.append(StepInfo(
                step_num=int(args[0].strip()),
                action=action,
                params=args[1].strip(),
                precondition=args[2].strip().strip("'"),
                postcondition=args[3].strip().strip("'"),
                constraint=args[4].strip(),
            ))

    return AllStepsForActionResponse(
        predicate="get_all_steps_for_action",
        action=action,
        steps=steps,
    )
