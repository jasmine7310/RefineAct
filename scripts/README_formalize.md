# Formalize Test Cases Script

This script processes test cases from JSON files, formalizing user instructions to Prolog and refining them into concrete action sequences.

## Prerequisites

1. Install required dependencies:
```bash
pip install openai python-dotenv
```

2. Set up your OpenAI API key in a `.env` file in the project root:
```
OPENAI_API_KEY=your_api_key_here
```

## Usage

### Basic Usage

Process the five test cases:
```bash
python scripts/formalize_test_cases.py assets/five_test_cases.json
```

This will add a `prolog_program` field to each test case in the JSON file.

### Advanced Options

```bash
# Save to a different output file
python scripts/formalize_test_cases.py assets/five_test_cases.json -o assets/formalized_cases.json

# Skip test cases that already have prolog_program
python scripts/formalize_test_cases.py assets/five_test_cases.json --skip-existing

# Use different models
python scripts/formalize_test_cases.py assets/five_test_cases.json \
  --formalization-model gpt-4o-mini-2024-07-18 \
  --refinement-model o3-mini-2025-01-31
```

### Command-Line Arguments

- `input_path`: Path to input JSON file with test cases (required)
- `-o, --output`: Path to output JSON file (defaults to input path)
- `--formalization-model`: LLM model for formalization (default: gpt-4o-mini-2024-07-18)
- `--refinement-model`: LLM model for refinement (default: o3-mini-2025-01-31)
- `--skip-existing`: Skip test cases that already have prolog_program

## Output Format

The script adds a `prolog_program` field to each test case containing the complete refined Prolog program:

```json
{
    "name": "official_2",
    "User Instruction": "Please grant the delivery person...",
    "prolog_program": "user_goal(grant_access, ...).\naction(...).\n...",
    ...
}
```

If formalization or refinement fails, error fields will be added instead:
- `formalization_error`: Error message if formalization failed
- `processing_error`: Error message if any other processing step failed

## Example

```bash
# Process the five test cases
cd /Users/fraolbatole/Documents/GitHub/ToolEmuLocal
python scripts/formalize_test_cases.py assets/five_test_cases.json

# Output will show progress for each case:
# Processing 1/5: official_2
# 1. Formalizing...
# ✓ Formalization successful
# 2. Refining...
# ✓ Refinement successful
# ...
```

## Notes

- The script uses two-stage processing: formalization (intent → Prolog) followed by refinement (abstract → concrete actions)
- Each stage includes retry logic with error feedback
- Prolog syntax is validated after each attempt
- Progress and results are printed to console during processing

