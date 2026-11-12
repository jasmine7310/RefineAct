"""
Formalize and Refine Test Cases.

This script processes test cases from JSON, formalizes user instructions
to Prolog, refines them into concrete action sequences, and saves the
resulting Prolog programs back to the JSON file.
"""

import json
import os
import sys
import time
from dotenv import load_dotenv
from pathlib import Path

# Add parent directory to path to import toolemu
sys.path.insert(0, str(Path(__file__).parent.parent))

from toolemu.formalization import (
    IntentFormalizer,
    FormalizationConfig,
    FormalizationError,
    GoalRefiner,
    RefinementConfig
)

load_dotenv()


def extract_case_number(case_name: str) -> int:
    """
    Extract case number from case name.
    
    Args:
        case_name: Case name like "official_2" or "official_128"
    
    Returns:
        Case number as integer
    """
    parts = case_name.split('_')
    if len(parts) >= 2:
        try:
            return int(parts[-1])
        except ValueError:
            pass
    return 0


def formalize_test_cases(
    input_path: str,
    output_path: str = None,
    formalization_model: str = "gpt-4o-mini-2024-07-18",
    refinement_model: str = "gpt-5-mini-2025-08-07",
    skip_existing: bool = False
):
    """
    Formalize and refine test cases from a JSON file.
    
    Args:
        input_path: Path to input JSON file with test cases
        output_path: Path to output JSON file (defaults to input_path)
        formalization_model: LLM model for formalization
        refinement_model: LLM model for refinement
        skip_existing: If True, skip test cases that already have prolog_program
    """
    # Check for API key
    if not os.getenv("OPENAI_API_KEY"):
        print("Error: OPENAI_API_KEY environment variable not set.")
        print("Please set it in your .env file or environment.")
        return
    
    # Import OpenAI
    try:
        import openai
        llm_client = openai
    except ImportError:
        print("Error: OpenAI package not installed.")
        print("Run: pip install openai")
        return
    
    # Set output path
    if output_path is None:
        output_path = input_path

    # Start timing the pipeline
    start_time = time.time()

    # Load test cases
    print(f"Loading test cases from: {input_path}")
    with open(input_path, 'r') as f:
        test_cases = json.load(f)
    
    print(f"Loaded {len(test_cases)} test cases")
    print("=" * 80)
    
    # Configure formalization and refinement
    formalization_config = FormalizationConfig(
        llm_model=formalization_model,
        temperature=0.0,
        max_retries=3
    )
    
    refinement_config = RefinementConfig(
        llm_model=refinement_model,
        temperature=0,
        max_retries=3
    )
    
    # Create formalizer and refiner
    formalizer = IntentFormalizer(llm_client=llm_client, config=formalization_config)
    refiner = GoalRefiner(llm_client=llm_client, config=refinement_config)
    
    # Process each test case
    for i, test_case in enumerate(test_cases):
        case_name = test_case.get("name", f"case_{i}")
        user_instruction = test_case.get("User Instruction", "")
        
        print(f"\nProcessing {i + 1}/{len(test_cases)}: {case_name}")
        print("-" * 80)
        
        # Skip if already has prolog_program and skip_existing is True
        if skip_existing and "prolog_program" in test_case:
            print(f"✓ Skipping (already has prolog_program)")
            continue
        
        if not user_instruction:
            print(f"✗ Skipping (no User Instruction)")
            continue
        
        print(f"User Instruction: {user_instruction[:100]}...")
        
        try:
            # Step 1: Formalize the instruction
            print("\n1. Formalizing...")
            underspec = test_case.get("Underspecifications", {})
            underspec_items = [
                item
                for items in underspec.values()
                for item in items
            ] if isinstance(underspec, dict) else list(underspec)

            underspec_text = "\n".join(f"- {item}" for item in underspec_items) if underspec_items else "- None"
            achievements = test_case.get("Expected Achievements", [])
            achievements_text = "\n".join(f"- {item}" for item in achievements) if achievements else "- None"

            context_str = f"""Underspecifications (things the user left unclear):
{underspec_text}

Expected Behavior:
{achievements_text}"""

            formalized_prolog = formalizer.formalize(user_instruction, context=context_str)
            print("✓ Formalization successful")
            print(f"Formalized Prolog:\n{formalized_prolog}\n")

            # Step 2: Refine the formalized goal
            print("2. Refining...")
            case_num = extract_case_number(case_name)

            risky_outcomes = test_case.get("Potential Risky Outcomes", [])
            risky_outcomes_text = "\n".join(f"- {item}" for item in risky_outcomes) if risky_outcomes else "- None"
            risky_actions = test_case.get("Potential Risky Actions", [])
            risky_actions_text = "\n".join(f"- {item}" for item in risky_actions) if risky_actions else "- None"

            refinement_context_str = f"""Underspecifications:
{underspec_text}

Expected Achievements:
{achievements_text}

Potential Risky Outcomes:
{risky_outcomes_text}

Potential Risky Actions:
{risky_actions_text}"""

            refined_plan = refiner.refine(formalized_prolog, case_num, context=refinement_context_str)
            print("✓ Refinement successful")
            
            # Save the Prolog program to the test case
            test_case["prolog_program"] = refined_plan.prolog_program
            
            print(f"\nComplete Prolog Program:")
            print("-" * 40)
            for line in refined_plan.prolog_program.split('\n'):
                if line.strip():
                    print(f"  {line}")
            
        except FormalizationError as e:
            print(f"✗ Formalization failed: {e}")
            test_case["prolog_program"] = None
            test_case["formalization_error"] = str(e)
            
        except Exception as e:
            print(f"✗ Processing failed: {e}")
            test_case["prolog_program"] = None
            test_case["processing_error"] = str(e)
    
    # Save the updated test cases
    print("\n" + "=" * 80)
    print(f"Saving updated test cases to: {output_path}")
    
    with open(output_path, 'w') as f:
        json.dump(test_cases, f, indent=4)
    
    # Stop timing and calculate total time
    end_time = time.time()
    total_time = end_time - start_time

    # Summary
    successful = sum(1 for tc in test_cases if tc.get("prolog_program"))
    print(f"\nSummary:")
    print(f"  Total cases: {len(test_cases)}")
    print(f"  Successful: {successful}")
    print(f"  Failed: {len(test_cases) - successful}")
    print(f"  Total time: {total_time:.2f} seconds")
    print("=" * 80)


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Formalize and refine test cases from JSON"
    )
    parser.add_argument(
        "input_path",
        type=str,
        help="Path to input JSON file with test cases"
    )
    parser.add_argument(
        "-o", "--output",
        type=str,
        default=None,
        help="Path to output JSON file (defaults to input path)"
    )
    parser.add_argument(
        "--formalization-model",
        type=str,
        default="gpt-4o-mini-2024-07-18",
        help="LLM model for formalization"
    )
    parser.add_argument(
        "--refinement-model",
        type=str,
        default="o3-mini-2025-01-31",
        help="LLM model for refinement"
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip test cases that already have prolog_program"
    )
    
    args = parser.parse_args()
    
    formalize_test_cases(
        input_path=args.input_path,
        output_path=args.output,
        formalization_model=args.formalization_model,
        refinement_model=args.refinement_model,
        skip_existing=args.skip_existing
    )


if __name__ == "__main__":
    main()

