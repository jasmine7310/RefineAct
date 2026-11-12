import argparse
import datetime
import os
import os.path as osp
import subprocess
import sys
import time

from toolemu.agents import AGENT_TYPES, SIMULATORS
from toolemu.dataloader import DataLoader
from toolemu.evaluators import EVALUATORS
from toolemu.utils import llm_register_args
from toolemu.utils.llm import AVAILABLE_MODEL_NAMES

# format YYYY_MM_DD__HH_MM_SS
NOW = datetime.datetime.now().strftime("%Y_%m_%d__%H_%M_%S")

EXECUTE_SCRIPT = "scripts/emulate.py"
EVALUATE_SCRIPT = "scripts/evaluate.py"
READRESULTS_SCRIPT = "scripts/helper/read_eval_results.py"
PROJECT_ROOT = osp.abspath(osp.join(osp.dirname(__file__), os.pardir))
RESULTS_DIR = osp.join(PROJECT_ROOT, "results")
LOG_FILE_PATH = osp.join(RESULTS_DIR, f"run_{NOW}.log")
TRAJ_DIR = osp.join(RESULTS_DIR, "trajectories")
os.makedirs(TRAJ_DIR, exist_ok=True)
TRAJ_LOG_FILE_PATH = osp.join(TRAJ_DIR, "traj_log.log")

parser = argparse.ArgumentParser()
llm_register_args(parser, prefix="agent")
DataLoader.register_args(parser, default_input_path="./assets/five_test_cases_formal.json")

# Override shuffle to default to True
parser.set_defaults(shuffle=True)
parser.add_argument("--dump-dir", "-du", type=str, default="./dumps/trajectories")
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
    default="adv_thought",
    choices=list(SIMULATORS.keys()),
)
parser.add_argument(
    "--simulator-model-name",
    type=str,
    default=None,
    choices=AVAILABLE_MODEL_NAMES,
    help="Model for the tool simulator (default: the emulate script's default)",
)
parser.add_argument(
    "--evaluator-model-name",
    type=str,
    default=None,
    choices=AVAILABLE_MODEL_NAMES,
    help="Model for the evaluators (default: the evaluate script's default)",
)
parser.add_argument("--batch-size", "-bs", type=int, default=None, help="batch size")
parser.add_argument("--auto", "-auto", action="store_true", help="auto mode")
parser.add_argument(
    "--verified-agent",
    "-verified",
    action="store_true",
    help="Use the verified zero-shot agent variant",
)
args = parser.parse_args()

# Timing variables
pipeline_start_time = time.time()
setup_start_time = time.time()

def run_command(cmd, need_confirm=True):
    print("Command:", cmd)
    if not args.auto and need_confirm and input("Continue? (y/n): ") != "y":
        raise RuntimeError("User aborted.")
    if os.system(cmd) != 0:
        raise RuntimeError(f"Command failed: {cmd}")


os.makedirs(RESULTS_DIR, exist_ok=True)

cases = DataLoader.from_args(args, item_name="case")
print(f"You are going to run {len(cases)} cases.")
if not args.auto and input("Continue? (y/n): ") != "y":
    exit()

setup_end_time = time.time()
emulation_start_time = time.time()

os.makedirs(args.dump_dir, exist_ok=True)
cmd = (
    f"python {EXECUTE_SCRIPT} -inp {args.input_path} -du {args.dump_dir} -outsuf _{NOW} "
    f" -trajlog {TRAJ_LOG_FILE_PATH} "
    f" -atp {args.agent_type} -stp {args.simulator_type} -am {args.agent_model_name} -si {args.start_index}"
)
if args.simulator_model_name is not None:
    cmd += f" -sm {args.simulator_model_name}"
if args.trunc_num is not None:
    cmd += f" -tn {args.trunc_num}"
if args.batch_size is not None:
    cmd += f" -bs {args.batch_size}"
if args.verified_agent:
    cmd += " -verified"
run_command(cmd)
emulation_end_time = time.time()
evaluation_start_time = time.time()

output_path = os.path.join(
    args.dump_dir,
    f"traj_sim_{args.simulator_type}_agent_{args.agent_model_name}_{args.agent_type}_{NOW}",
)
print("The trajectories are saved to", output_path)

# evaluate all trajectories for different evaluators
cmd = f"python {EVALUATE_SCRIPT} -inp {output_path}.jsonl"
if args.evaluator_model_name is not None:
    cmd += f" -em {args.evaluator_model_name}"
if args.batch_size is not None:
    cmd += f" -bs {args.batch_size}"
for ev in EVALUATORS.keys():
    run_command(f"{cmd} -ev {ev}")

evaluation_end_time = time.time()
results_start_time = time.time()

# read evaluation results and persist summary
# sys.executable, not "python": on Windows a bare "python" started from a venv
# resolves to the base interpreter, which does not have the project's packages.
read_results_cmd = [sys.executable, READRESULTS_SCRIPT, output_path]
result = subprocess.run(
    read_results_cmd,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    check=True,
)
summary_text = result.stdout or ""
print(summary_text, end="" if summary_text.endswith("\n") else "\n")

results_end_time = time.time()
pipeline_end_time = time.time()

# Calculate timing durations
setup_duration = setup_end_time - setup_start_time
emulation_duration = emulation_end_time - emulation_start_time
evaluation_duration = evaluation_end_time - evaluation_start_time
results_duration = results_end_time - results_start_time
total_duration = pipeline_end_time - pipeline_start_time

with open(LOG_FILE_PATH, "w", encoding="utf-8") as log_file:
    log_file.write(f"Timestamp: {NOW}\n")
    log_file.write("Configuration:\n")
    for key, value in sorted(vars(args).items()):
        log_file.write(f"  {key}: {value}\n")
    log_file.write("\nTiming Information:\n")
    log_file.write(f"  Setup Phase: {setup_duration:.2f} seconds\n")
    log_file.write(f"  Emulation Phase: {emulation_duration:.2f} seconds\n")
    log_file.write(f"  Evaluation Phase: {evaluation_duration:.2f} seconds\n")
    log_file.write(f"  Results Processing: {results_duration:.2f} seconds\n")
    log_file.write(f"  Total Pipeline Time: {total_duration:.2f} seconds\n")
    log_file.write("\nEvaluation Summary:\n")
    log_file.write(summary_text)
    if not summary_text.endswith("\n"):
        log_file.write("\n")

print(f"Evaluation summary saved to {LOG_FILE_PATH}")
