"""Toolkit vocabulary extraction for Prolog predicate generation."""

import os
from typing import List

from toolemu.tools import get_toolkits_by_names
from toolemu.tools.tool_interface import BaseToolkit, FunctionTool
from toolemu.utils import get_toolkit_names, read_file


def generate_toolkit_summaries(case_num: int = 0) -> str:
    """
    Generate Prolog predicate vocabulary from toolkit specifications.
    
    Loads a case from all_cases.json, extracts toolkit names from it,
    retrieves the toolkits, and generates vocabulary.
    
    Args:
        case_num: Case number/index from all_cases.json (default: 0)
        
    Returns:
        String containing Prolog predicate templates with descriptions
        
    Example output:
        - send_email(recipient, subject, body)  % Send an email message
        - delete_file(file_path)  % Delete a file from the system
    """
    # Load case from all_cases.json
    cases_path = os.path.join(
        os.path.dirname(__file__), 
        "../../assets/all_cases.json"
    )
    cases = read_file(cases_path)
    
    # Get the specific case
    if case_num >= len(cases):
        raise ValueError(f"Case number {case_num} out of range (max: {len(cases) - 1})")
    
    case = cases[case_num]

    # print(f"Case: {case}")
    
    # Extract toolkit names from the case
    toolkit_names = get_toolkit_names(case)
    
    # print(f"Toolkit names: {toolkit_names}")

    # Get toolkits by names
    toolkits = get_toolkits_by_names(toolkit_names)
    
    # Extract tool names and summaries from all toolkits
    tool_descriptions = []
    for toolkit in toolkits:
        for tool in toolkit.tools:
            parameters = getattr(tool, "parameters", None) or []
            param_list = ", ".join(param["name"].lower() for param in parameters)
            signature = f"{tool.name.lower()}({param_list})" if param_list else f"{tool.name.lower()}()"
            tool_descriptions.append(f"- {signature}  % {tool.summary}")
    
    toolkit_desc = "\n".join(tool_descriptions)

    return toolkit_desc

def extract_domain_predicates(task_type: str = "translate") -> str:
    """
    Generate standard domain predicates for user intent formalization.

    These are higher-level predicates that represent user goals, constraints,
    and requirements, independent of specific tools.

    Args:
        task_type: Either "translate" or "refine". "refine" includes additional
                  predicates for refinement tasks. "traslate" includes original formalization predicates. 

    Returns:
        String containing standard Prolog predicate templates
    """
    if task_type == "translate":
        base_predicates = [
            "# Standard Intent Predicates",
            "- user_goal(GoalName, [param(Name,Value), ...], [Condition, ...])  % EXACTLY ONE per intent. GoalName captures the overarching goal as a single atom.",
        ]
    elif task_type == "refine":
        base_predicates = [
            "# Allowed Predicates (output ONLY these)",
            "- refined_step(StepNumber, Action, [param(Name,Value), ...], Precondition, Postcondition, Constraint)",
            "  % Constraint is 'none' or constraint(Type, Description). Type: safety|security|privacy|ethics",
            "- risky_action(Action, Pattern, Disposition)",
            "  % Pattern: a substring that, if found in the action's runtime input, triggers the Disposition.",
            "  % Disposition: 'reject' (block unconditionally) | 'user_consent' (require explicit user approval).",
        ]
    else:
        raise ValueError(f"Unknown task_type: {task_type}")

    return '\n'.join(base_predicates)



