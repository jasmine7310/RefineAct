"""Prolog syntax validation using SWI-Prolog subprocess."""

import re
import tempfile
import os
import subprocess
from typing import Tuple


def validate_prolog_syntax(prolog_code: str, validation_type: str = "translate") -> Tuple[bool, str]:
    """
    Validate Prolog syntax and optionally run queries using SWI-Prolog subprocess.

    Args:
        prolog_code: Prolog code string to validate
        validation_type: Either "translate" or "refine".
                        - "translate": Only check syntax and singleton warnings
                        - "refine": Check syntax, singleton warnings, and run temporal_requirement queries

    Returns:
        Tuple of (is_valid, output_message)
        - is_valid: True if syntax is valid (and query succeeds for refine), False otherwise
        - output_message: Query output and results, or error description if invalid
    """
    if not prolog_code or not prolog_code.strip():
        return False, "Empty Prolog code provided"

    temp_path = None

    try:
        # Use the code exactly as provided so validation reflects the real output
        code = prolog_code.strip()

        # Write code to temporary file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.pl', delete=False) as f:
            f.write(code)
            temp_path = f.name

        if validation_type == "translate":
            # For translate: just load the file and check for syntax errors and singleton warnings
            result = subprocess.run(
                ['swipl', '-q', '-l', temp_path, '-g', 'halt(0)'],
                capture_output=True,
                text=True,
                timeout=10
            )
            success_message = "Syntax check passed"
        else:
            # For refine: verify refined_step/6 predicates are well-formed,
            # and if risky_action/3 facts exist they are also well-formed.
            # risky_action is optional, so we only validate it when present.
            refine_goal = (
                "(forall(refined_step(_, _, _, _, _, _), true) -> true ; (write('No refined_step/6 found'), nl, halt(1))),"
                "(predicate_property(risky_action(_,_,_), defined) "
                "-> forall(risky_action(_, _, _), true) ; true),"
                "halt(0)"
            )
            result = subprocess.run(
                ['swipl', '-q', '-l', temp_path, '-g', refine_goal],
                capture_output=True,
                text=True,
                timeout=10
            )
            success_message = "Query succeeded"

        # Combine stdout and stderr for full output
        failed_output = f"\nSTDERR:\n{result.stderr}\n\nRETURN CODE: {result.returncode}"

        # Check for singleton variable warnings in stderr
        if "Singleton" in result.stderr:
            # Return stderr content as the error message for singleton warnings
            return False, f"Singleton warning:\n{failed_output}"

        # Check for errors
        if result.returncode != 0:
            return False, f"{'Query' if validation_type == 'refine' else 'Syntax check'} failed:\n{failed_output}"

        return True, success_message

    except subprocess.TimeoutExpired:
        return False, "Prolog validation timeout"
    except FileNotFoundError:
        return False, "SWI-Prolog (swipl) not found. Please install SWI-Prolog."
    except Exception as e:
        return False, f"Prolog validation error: {str(e)}"

    finally:
        # Clean up temporary file
        if temp_path and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except:
                pass


def execute_prolog_query(prolog_program: str, query: str) -> Tuple[bool, str]:
    """
    Execute a Prolog query against a Prolog program.

    Args:
        prolog_program: Complete Prolog program as a string
        query: Prolog query to execute (without the final period)

    Returns:
        Tuple of (success, output)
        - success: True if query executed without errors, False otherwise
        - output: Query results or error message
    """
    if not prolog_program or not prolog_program.strip():
        return False, "Empty Prolog program provided"

    if not query or not query.strip():
        return False, "Empty query provided"

    temp_path = None

    try:
        # Write program to temporary file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.pl', delete=False) as f:
            f.write(prolog_program.strip())
            temp_path = f.name
        
        query_str = query.strip()
        
        # Construct a goal that:
        # - Prints all solutions using forall
        # - Checks if at least one solution exists
        # - Exits with appropriate code
        query_goal = (
            f"(forall({query_str}, (write_canonical({query_str}), nl)), {query_str}) "
            f"-> halt(0) ; halt(1)"
        )
        
        result = subprocess.run(
            ['swipl', '-q', '-l', temp_path, '-g', query_goal],
            capture_output=True,
            text=True,
            timeout=30  # Longer timeout for queries
        )

        # Check for errors
        if result.returncode != 0:
            return False, f"Query failed:\nSTDERR: {result.stderr}\nSTDOUT: {result.stdout}"

        # Return successful output
        # print(result.stdout.strip())
        return True, result.stdout.strip()

    except subprocess.TimeoutExpired:
        return False, "Query execution timeout"
    except FileNotFoundError:
        return False, "SWI-Prolog (swipl) not found. Please install SWI-Prolog."
    except Exception as e:
        return False, f"Query execution error: {str(e)}"

    finally:
        # Clean up temporary file
        if temp_path and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except:
                pass
