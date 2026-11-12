"""
Emulate the agent's tool-use trajectories.

Usage: python scripts/emulate.py -inp <input_cases_file> -atp <agent_type> -stp <simulator_type> -ctp <case_type>
"""

import argparse
import os
import random

import anthropic
import openai.error
from dotenv import load_dotenv
from toolemu.agent_executor_builder import build_agent_executor
from toolemu.agents import AGENT_TYPES, SIMULATORS
from toolemu.dataloader import DataLoader
from toolemu.executors import FuncExecutorWithRetry
from toolemu.tools import *
from toolemu.utils import (
    case_to_input_dict,
    filter_keys,
    get_toolkit_names,
    llm_register_args,
    load_openai_llm_with_args,
    replace_agent_action_with_list,
    construct_simple_trajec,
    append_file,
)
from toolemu.utils.io import set_formal_cases_path
from toolemu.utils.llm import ClaudeRefusalError
from toolemu.utils.my_typing import *

load_dotenv()
ROLES = ["agent", "simulator"]

parser = argparse.ArgumentParser()
for role in ROLES:
    llm_register_args(parser, prefix=role)
DataLoader.register_args(parser)
FuncExecutorWithRetry.register_args(
    parser, default_num_retries=5, default_batch_size=5, default_timeout=1800
)
parser.add_argument("--dump-dir", "-du", type=str, default="./dumps/trajectories")
parser.add_argument(
    "--output-file-suffix",
    "-outsuf",
    type=str,
    default="",
)
parser.add_argument(
    "--agent-type",
    "-atp",
    type=str,
    default="naive",
    choices=AGENT_TYPES,
)
parser.add_argument(
    "--simulator-type",
    "-stp",
    type=str,
    default="std_thought",
    choices=list(SIMULATORS.keys()),
)
parser.add_argument("--max-iterations", "-mi", type=int, default=15)
parser.add_argument("--verbose", "-v", action="store_true")
parser.add_argument("--random-seed", "-seed", type=int, default=42)
parser.add_argument(
    "--trajectory-log-path",
    "-trajlog",
    type=str,
    default="trajectories/traj_log.log",
)
parser.add_argument(
    "--verified-agent",
    "-verified",
    action="store_true",
    help="Use the verified zero-shot agent variant",
)

args = parser.parse_args()
random.seed(args.random_seed)


def resolve_formal_cases_path(input_path: str) -> str:
    """Resolve the formalized cases path for validator lookups."""
    if input_path.endswith("_formal.json"):
        return input_path
    if input_path.endswith(".json"):
        candidate = input_path[:-5] + "_formal.json"
        if os.path.exists(candidate):
            return candidate
    return input_path


set_formal_cases_path(resolve_formal_cases_path(args.input_path))
if args.trajectory_log_path is None:
    args.trajectory_log_path = os.path.join(
        args.dump_dir,
        (
            f"traj_log_{args.simulator_type}_agent_{args.agent_model_name}"
            f"_{args.agent_type}{args.output_file_suffix}.log"
        ),
    )


def main():
    llms = {role: load_openai_llm_with_args(args, prefix=role) for role in ROLES}
    cases = DataLoader.from_args(args, return_mode="with_idx", item_name="case")
    runner = FuncExecutorWithRetry.from_args(args)
    os.makedirs(args.dump_dir, exist_ok=True)
    output_path = os.path.join(
        args.dump_dir,
        (
            f"traj_sim_{args.simulator_type}_agent_{args.agent_model_name}"
            f"_{args.agent_type}{args.output_file_suffix}.jsonl"
        ),
    )

    def generate_trajectory(case_with_idx):
        case_idx, case = case_with_idx["idx"], case_with_idx["item"]
        agent_executer = build_agent_executor(
            get_toolkit_names(case),
            llms["agent"],
            llms["simulator"],
            agent_type=args.agent_type,
            simulator_type=args.simulator_type,
            verbose=args.verbose,
            max_iterations=args.max_iterations,
            verified=args.verified_agent,
            case_idx = case_idx,
        )
        inputs = filter_keys(case_to_input_dict(case), agent_executer.input_keys)
        try:
            outputs = agent_executer(inputs)
            failed_item = None
        except (
            openai.error.InvalidRequestError,
            anthropic.BadRequestError,
            ClaudeRefusalError,
        ) as e:
            print(f"{case_idx}: {str(e)}")
            outputs = {"error": str(e)}
            failed_item = case_with_idx
        else:
            traj_dict = dict(outputs)
            traj_input = inputs.get("input")
            if traj_input is None:
                traj_input = case_to_input_dict(case).get("input")
            traj_dict["input"] = traj_input
            simple_traj = construct_simple_trajec(traj_dict)
            # print(f"=== Trajectory for case {case_idx} ===\n{simple_traj}\n")
            if args.trajectory_log_path:
                append_file(
                    args.trajectory_log_path,
                    f"Case {case_idx}\n{simple_traj}",
                    seperator="\n" + "=" * 80 + "\n",
                )
        outputs = replace_agent_action_with_list(outputs)  # ad-hoc fix
        outputs["case"] = case
        outputs["case_idx"] = case_idx
        # Attach validator log from verified agent for evaluator visibility
        if args.verified_agent and hasattr(agent_executer, 'agent'):
            agent_obj = agent_executer.agent
            if hasattr(agent_obj, 'validator_log'):
                outputs["validator_log"] = list(agent_obj.validator_log)
        return failed_item, outputs

    runner.run(generate_trajectory, output_path, cases)
    print(
        "You may want to use scripts to convert the result jsonl file "
        f"{output_path} to json for easier reading."
    )


if __name__ == "__main__":
    main()
