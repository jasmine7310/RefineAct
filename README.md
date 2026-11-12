# RefineAct — Replication Package

RefineAct extends [ToolEmu](https://github.com/ryoungj/ToolEmu), an LLM-based emulation framework for evaluating the safety and helpfulness of tool-using LLM agents. On top of ToolEmu's emulation and evaluation pipeline, RefineAct introduces a ** refinement layer** that translates natural-language user instructions into Prolog programs, refines them into concrete action sequences, and optionally validates agent behaviour at runtime via a verified agent variant.

## Prerequisites

- Python >= 3.6
- [SWI-Prolog](https://www.swi-prolog.org/) (required by `pyswip` for Prolog validation)
- An OpenAI API key

## Installation

```bash
# Clone the repository
Download the RefineAct replication package

# Create and activate a virtual environment
python -m venv venv
source venv/bin/activate

# Install the package and dependencies
pip install -e .

# Configure your API key
echo "OPENAI_API_KEY=<your-key>" > .env
```

## Running Experiments

Each domain has a dedicated runner script that executes the full pipeline (emulation → evaluation → results summary) on its formal test cases.

### Usage

```bash
./run_<domain>.sh [--verified] [--trunc-num NUM]
```

| Flag | Description |
|---|---|
| `--verified` | Enables the verified agent variant that validates actions against the Prolog specification. |
| `--trunc-num NUM` | Limits the number of test cases to run (defaults vary per domain). |

### Example: Communication Domain

```bash
# Run all 17 communication cases with the standard agent
./run_communication.sh

# Run with the verified agent
./run_communication.sh --verified

# Run only the first 5 cases with the verified agent
./run_communication.sh --verified --trunc-num 5
```

### Example: Finance Domain

```bash
# Run all 30 finance cases
./run_finance.sh

# Run 10 finance cases with the verified agent
./run_finance.sh --verified --trunc-num 10
```

### Available Runner Scripts

| Script | Domain | Default Case Count |
|---|---|---|
| `run_communication.sh` | Communication | 17 |
| `run_data_management.sh` | Data Management | 35 |
| `run_development.sh` | Development | 35 |
| `run_finance.sh` | Finance | 30 |
| `run_iot.sh` | IoT | 35 |


### Formalizing New Test Cases

To add Prolog specifications to custom test cases:

```bash
python scripts/formalize_test_cases.py <input.json> [-o <output.json>] [--skip-existing]
```

Refer to `scripts/README_formalize.md` for details.

## License

Apache 2.0 — see [LICENSE](LICENSE).

## Acknowledgements

RefineAct builds directly on the [ToolEmu](https://github.com/ryoungj/ToolEmu) framework by Honghua Dong and Yangjun Ruan. The original emulation, evaluation, and generation infrastructure is retained; RefineAct adds the formalization, refinement, and verification layers described above.
