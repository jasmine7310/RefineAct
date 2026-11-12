"""Check that everything needed to run the benchmark is in place.

Prints OK or FAIL for each item and exits non-zero if any item failed.
Run from the repository root:  PYTHONPATH=$PWD python scripts/check_setup.py [--live]

This script is LLM-generated.
"""

import argparse
import importlib
import importlib.metadata as metadata
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable
from functools import partial
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
ROLES = ("agent", "simulator", "evaluator")
DOMAINS = ("communication", "data_management", "development", "finance", "iot")
# Required version prefix per package; None means any version.
PACKAGES: dict[str, str | None] = {
    "numpy": "1.26.4",
    "langchain": "0.0.277",
    "openai": "0.28",
    "tiktoken": "0.9.0",
    "python-dotenv": "1.0.0",
    "pydantic": "1.",
    "pandas": None,
    "tqdm": None,
    "rouge-score": None,
    "anthropic": None,
    "wikipedia": None,
    "procoder": None,
}
NATIVE_URL_VARS = {"openai": "OPENAI_API_BASE", "anthropic": "ANTHROPIC_BASE_URL"}
PROLOG_OK = "user_goal(a, b, c).\n"
PROLOG_REFINED = "refined_step(a, b, c, d, e, f).\n"

Check = Callable[[], str]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def check_python() -> str:
    version = sys.version_info[:3]
    require((3, 10) <= version[:2] <= (3, 12), f"Python {version} is outside 3.10-3.12")
    return ".".join(map(str, version))


def check_package(name: str, prefix: str | None) -> str:
    installed = metadata.version(name)
    require(
        prefix is None or installed.startswith(prefix),
        f"installed {installed}, expected {prefix}",
    )
    return installed


def check_import(module: str) -> str:
    importlib.import_module(module)
    return "imported"


def check_swipl() -> str:
    path = shutil.which("swipl")
    require(
        path is not None,
        "swipl not on PATH (install SWI-Prolog, e.g. apt-get install swi-prolog)",
    )
    result = subprocess.run(
        ["swipl", "--version"], capture_output=True, text=True, timeout=10
    )
    return result.stdout.strip()


def check_prolog() -> str:
    from toolemu.formalization.validator import (
        execute_prolog_query,
        validate_prolog_syntax,
    )

    ok, message = validate_prolog_syntax(PROLOG_OK, "translate")
    require(ok, f"valid program rejected: {message}")
    ok, message = validate_prolog_syntax(PROLOG_REFINED, "refine")
    require(ok, f"refined program rejected: {message}")
    ok, _ = validate_prolog_syntax(PROLOG_OK, "refine")
    require(not ok, "a program without refined_step/6 was accepted")
    ok, message = execute_prolog_query(PROLOG_OK, "user_goal(A, b, c)")
    require(ok and "user_goal(a,b,c)" in message, f"query failed: {message}")
    return "swipl runs, validates, and answers queries"


def role_args(role: str, argv: list[str]) -> argparse.Namespace:
    from toolemu.utils.llm import llm_register_args

    parser = argparse.ArgumentParser()
    llm_register_args(parser, prefix=role)
    return parser.parse_args(argv)


def check_role(role: str) -> str:
    from toolemu.utils.llm import get_model_name, resolve_credentials

    model = get_model_name(getattr(role_args(role, []), f"{role}_model_name"))
    provider, api_key, base_url = resolve_credentials(role, model)
    key_var = f"{provider.upper()}_API_KEY"
    require(
        bool(api_key or os.environ.get(key_var)),
        f"no API key: set REFINEACT_API_KEY or {key_var}",
    )
    url = base_url or os.environ.get(NATIVE_URL_VARS[provider], "")
    require(
        not url or url.startswith(("http://", "https://")),
        f"base URL {url!r} is not an http(s) URL",
    )
    require(
        not url.rstrip("/").endswith(("/chat/completions", "/messages")),
        "base URL ends with an endpoint path; use the base only (e.g. .../api/v1)",
    )
    return f"{model} via {provider}"


def check_live(role: str) -> str:
    from langchain.schema import HumanMessage

    from toolemu.utils.llm import load_openai_llm_with_args

    argv = [f"--{role}-max-tokens", "16", f"--{role}-max-retries", "0"]
    llm = load_openai_llm_with_args(role_args(role, argv), prefix=role)
    reply = llm.predict_messages([HumanMessage(content="Say hi")]).content
    return f"reply of {len(reply)} characters"


def check_cases(domain: str) -> str:
    path = ROOT / "assets" / "category" / f"{domain}_cases_formal.json"
    count = len(json.loads(path.read_text(encoding="utf-8")))
    require(count > 0, "no cases")
    return f"{count} cases"


def check_script(domain: str) -> str:
    path = ROOT / f"run_{domain}.sh"
    require(path.is_file(), "missing")
    require(os.access(path, os.X_OK), "not executable (chmod 755)")
    require(b"\r" not in path.read_bytes(), "has CRLF line endings")
    return "executable, LF"


def check_writable(name: str) -> str:
    directory = ROOT / name
    with tempfile.TemporaryFile(dir=directory if directory.is_dir() else ROOT):
        return f"{name}/ can be written"


def build_checks(live: bool) -> list[tuple[str, Check]]:
    checks: list[tuple[str, Check]] = [("python", check_python)]
    checks += [
        (f"package {n}", partial(check_package, n, v)) for n, v in PACKAGES.items()
    ]
    checks += [
        (f"import {m}", partial(check_import, m))
        for m in ("toolemu.agents", "toolemu.evaluators")
    ]
    checks += [("swipl installed", check_swipl), ("prolog validator", check_prolog)]
    checks += [(f"config {r}", partial(check_role, r)) for r in ROLES]
    checks += [(f"cases {d}", partial(check_cases, d)) for d in DOMAINS]
    checks += [(f"run_{d}.sh", partial(check_script, d)) for d in DOMAINS]
    checks += [(f"write {n}", partial(check_writable, n)) for n in ("dumps", "results")]
    if live:
        checks += [(f"live call {r}", partial(check_live, r)) for r in ROLES]
    return checks


def run_checks(checks: list[tuple[str, Check]]) -> int:
    """Print one line per check and return how many failed."""
    failures = 0
    for name, check in checks:
        try:
            print(f"OK    {name}: {check()}")
        except (
            Exception
        ) as error:  # report every failure instead of stopping at the first
            failures += 1
            print(f"FAIL  {name}: {type(error).__name__}: {error}")
    return failures


def main() -> None:
    parser = argparse.ArgumentParser(description="Check the benchmark setup.")
    parser.add_argument(
        "--live", action="store_true", help="make one tiny model call per role"
    )
    load_dotenv(ROOT / ".env")
    failures = run_checks(build_checks(parser.parse_args().live))
    print(f"\n{failures} failed" if failures else "\nall checks passed")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
