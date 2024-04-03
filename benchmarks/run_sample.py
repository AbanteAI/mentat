import json
import random
import subprocess
import sys
from pathlib import Path
from typing import Any

import tqdm
from git import Repo

from mentat import Mentat
from mentat.config import Config
from mentat.errors import SampleError
from mentat.git_handler import get_git_diff
from mentat.parsers.git_parser import GitParser
from mentat.sampler.sample import Sample
from mentat.sampler.utils import apply_diff_to_repo, get_active_snapshot_commit, setup_repo
from mentat.session_context import SESSION_CONTEXT


def setup_sample(
    sample: Sample, cwd: Path | str | None, skip_test_exec: bool = False
) -> tuple[Repo, Path, str, str | None]:
    setup_commit = sample.environment_setup_commit or sample.merge_base
    repo = setup_repo(
        url=sample.repo,
        cwd=cwd,
        commit=setup_commit,
        diff_merge_base=sample.diff_merge_base,
        diff_active=sample.diff_active,
    )
    cwd = Path(repo.working_dir)

    test_executable = None
    if not skip_test_exec and (sample.FAIL_TO_PASS or sample.PASS_TO_PASS):
        # If there's an environment_setup_commit, this is what it's needed for.
        try:
            test_executable = get_test_executable(Path(repo.working_dir))
        except SampleError as e:
            print(f"Error setting up virtual environment: {e}")
            print("Using default python executable instead.")
    if not test_executable:
        test_executable = sys.executable

    if sample.environment_setup_commit and sample.merge_base:
        # SWE-Bench samples have an environmental_setup_commit (above),
        # then a merge_base to checkout.
        repo.git.reset("--hard")
        repo.git.checkout(sample.merge_base)
        commit_active = sample.merge_base
    else:
        # Mentat Samples have an active diff which was set in setup_repo,
        # so here create a snapshot commit (to generate diff_edit against later)
        commit_active = get_active_snapshot_commit(repo)

    return repo, cwd, test_executable, commit_active


async def run_sample(sample: Sample, cwd: Path | str | None = None, config: Config | None = None) -> dict[str, Any]:
    """Run a sample using Mentat and return the resulting diff"""

    repo, cwd, test_executable, commit_active = setup_sample(sample, cwd)

    # Run sample in PythonClient
    paths = list[Path]()
    for a in sample.context:
        paths.append(Path(a))
    mentat = Mentat(cwd=cwd, paths=paths, config=config or Config())
    await mentat.startup()
    session_context = SESSION_CONTEXT.get()
    conversation = session_context.conversation
    cost_tracker = session_context.cost_tracker
    for msg in sample.message_history:
        if msg["role"] == "user":
            conversation.add_user_message(msg["content"])
        elif msg["role"] == "assistant":
            parsed_llm_response = GitParser().parse_llm_response(msg["content"])
            content = session_context.config.parser.file_edits_to_llm_message(parsed_llm_response)
            conversation.add_model_message(content, [], parsed_llm_response)
        else:
            raise SampleError(f"Invalid role found in message_history: {msg['role']}")
    prompt = sample.message_prompt
    if sample.hint_text:
        prompt += f"\n{80 * '-'}\nHint Text:\n{sample.hint_text}"
    await mentat.call_mentat_auto_accept(prompt)
    await mentat.shutdown()

    # Get the diff between pre- and post-edit
    transcript_messages = conversation.literal_messages.copy()

    message_eval = str(transcript_messages[-1].get("message", ""))
    diff_eval = get_git_diff(commit_active or "HEAD", cwd=cwd)

    test_results = None
    test_passed = None
    if sample.test_patch:
        apply_diff_to_repo(sample.test_patch, repo)
    if sample.FAIL_TO_PASS:
        tests = json.loads(sample.FAIL_TO_PASS)
        total = len(tests)
        passed = 0
        errors = list[dict[str, str]]()
        for test in tests:
            _passed, _error = get_test_result(test, cwd, test_executable)
            if _passed:
                passed += 1
            if _error:
                errors.append({"test": test, "error": _error})
        test_results = {
            "passed": passed,
            "total": total,
            "passed_percent": passed / total * 100,
            # "errors": errors,  # Too big, but useful for debugging
        }
        test_passed = passed == total

    return {
        "id": sample.id,
        "message_eval": message_eval,
        "diff_eval": diff_eval,
        "cost": cost_tracker.total_cost,
        "tokens": cost_tracker.total_tokens,
        "transcript": {
            "id": sample.id,
            "messages": transcript_messages,
        },
        "test_eval_results": test_results,
        "test_eval_passed": test_passed,
    }


test_requirements_for_repo = {
    "pvlib-python": [
        "setuptools",
        "pytest",
        "pytest-cov",
        "pytest-mock",
        "requests-mock",
        "pytest-timeout",
        "pytest-rerunfailures",
        "pytest-remotedata",
    ],
    "pydicom": ["setuptools", "pytest"],
    "sqlfluff": [
        "setuptools",
        "pytest",
        "pytest-cov",
        "pytest-mock",
        "Jinja2",
        "oyaml",
    ],
    "pyvista": [
        "setuptools",
        "pytest",
        "ipython",
        "ipywidgets",
        "ipykernel",
        "tqdm",
    ],
    "astroid": [
        "setuptools",
        "pytest",
        "attrs",
        "types-attrs",
        "nose",
        "numpy",
        "python-dateutil",
        "types-python-dateutil",
        "six",
        "types-six",
    ],
    "marshmallow": [
        "setuptools",
        "pytest",
        "pytz",
        "simplejson",
    ],
}


def get_test_executable(cwd: Path) -> str:
    """Rebuild every time with the latest setup."""

    venv_dir = cwd / ".venv"
    repo_name = cwd.name

    try:
        python_executable = "python3" if sys.platform != "win32" else "python"
        subprocess.run([python_executable, "-m", "venv", str(venv_dir)], check=True, cwd=cwd, capture_output=True)
    except Exception as e:
        raise SampleError(f"Error creating virtual environment: {e}")

    # Install as a pip module
    try:
        output = subprocess.run(
            [venv_dir / "bin" / "pip", "install", "-e", "."], check=True, cwd=cwd, capture_output=True
        )
        if output.returncode != 0:
            raise SampleError(f"Error installing sample as a pip module: {output.stderr}")
    except Exception as e:
        raise SampleError(f"Error installing sample as a pip module: {e}")

    # Requirements are hard-coded by repo
    if repo_name not in test_requirements_for_repo:
        raise SampleError(f"No requirements found for repo '{repo_name}'")
    requirements = test_requirements_for_repo[repo_name]

    # Install them all with pip
    try:
        output = subprocess.run(
            [venv_dir / "bin" / "pip", "install", *list(requirements)], check=True, cwd=cwd, capture_output=True
        )
        if output.returncode != 0:
            raise SampleError(f"Error installing requirements: {output.stderr}")
    except Exception as e:
        raise SampleError(f"Error installing requirements: {e}")

    return str(venv_dir / "bin" / "python")


def get_test_result(test: str, cwd: Path, test_executable: str) -> tuple[bool, str]:
    passed, error = False, ""
    command = [test_executable, "-m", "pytest"]
    if "[" in test:
        # Some tests include parameters, like "..is_valid[3.1415]".
        # Running '-k' over the whole suite is very slow.
        path, params = test.split("[", 1)
        params = params[:-1]  # Remove trailing ']'
        command += [path, "-k", params]
    else:
        command += [test]
    try:
        output = subprocess.run(
            command,
            capture_output=True,
            text=True,
            cwd=cwd,
        )
        if (output.returncode != 0 and output.stderr) or not output.stdout:
            raise SampleError(f"Test command failed: {output.stderr}")

        # Starting from the end, find the first line that contains "passed" or "failed"
        lines = output.stdout.splitlines()
        result_line = next(
            line for line in reversed(lines) if any(key in line for key in {"passed", "failed", "skipped"})
        )
        _passed = "passed" in result_line or "skipped" in result_line
        _failed = "failed" in result_line
        if _passed == _failed:
            raise SampleError(f"Could not determine test result from line: {result_line}")
        passed = _passed
        if _failed:
            raise SampleError("Test failed:\n" + "\n".join(lines))
    except (SampleError, StopIteration, Exception) as e:
        error = str(e)
    return passed, error


def validate_test_fields(sample: Sample) -> dict[str, Any]:
    test_results: dict[str, Any] = {
        "PASS_TO_PASS": {"passed": 0, "total": 0, "errors": []},
        "FAIL_TO_PASS_PRE": {"passed": 0, "total": 0, "errors": []},
        "FAIL_TO_PASS_POST": {"passed": 0, "total": 0, "errors": []},
    }

    if not sample.FAIL_TO_PASS and not sample.PASS_TO_PASS:
        return test_results

    repo, cwd, test_executable, _ = setup_sample(sample, None)

    # Run the PASS_TO_PASS test, expected to PASS
    if sample.PASS_TO_PASS:
        tests = json.loads(sample.PASS_TO_PASS)

        # There are sometimes hundreds of tests which take ~30 minutes to all complete.
        # Since we'll check all the FAIL_TO_PASS tests, here we just want to confirm the
        # environment is set up correctly, so we sample 10 tests.
        tests = random.sample(tests, min(10, len(tests)))

        # Iterate with tqdm
        for test in tqdm.tqdm(tests, desc="PASS_TO_PASS tests", unit="test"):
            test_results["PASS_TO_PASS"]["total"] += 1
            passed, error = False, ""
            try:
                passed, error = get_test_result(test, cwd, test_executable)
                if passed:
                    test_results["PASS_TO_PASS"]["passed"] += 1
                elif error:
                    raise SampleError(error)
            except SampleError as e:
                test_results["PASS_TO_PASS"]["errors"].append({"test": test, "error": str(e)})
    print("PASS_TO_PASS results: ", test_results["PASS_TO_PASS"])

    # Apply test patch
    if sample.test_patch:
        print("Applying test patch...")
        apply_diff_to_repo(sample.test_patch, repo)

    # Run FAIL_TO_PASS tests expected to FAIL
    if sample.FAIL_TO_PASS:
        tests = json.loads(sample.FAIL_TO_PASS)
        for test in tqdm.tqdm(tests, desc="FAIL_TO_PASS tests", unit="test"):
            test_results["FAIL_TO_PASS_PRE"]["total"] += 1
            passed, error = False, ""
            try:
                passed, error = get_test_result(test, cwd, test_executable)
                if passed:
                    test_results["FAIL_TO_PASS_PRE"]["passed"] += 1
                elif error:
                    raise SampleError(error)
            except SampleError as e:
                test_results["FAIL_TO_PASS_PRE"]["errors"].append({"test": test, "error": str(e)})
    print("FAIL_TO_PASS_PRE results: ", test_results["FAIL_TO_PASS_PRE"])

    # Apply golden patch
    if sample.diff_edit:
        print("Applying diff_edit...")
        apply_diff_to_repo(sample.diff_edit, repo)

    # Run FAIL_TO_PASS tests expected to PASS
    if sample.FAIL_TO_PASS:
        tests = json.loads(sample.FAIL_TO_PASS)
        for test in tqdm.tqdm(tests, desc="FAIL_TO_PASS tests", unit="test"):
            test_results["FAIL_TO_PASS_POST"]["total"] += 1
            passed, error = False, ""
            try:
                passed, error = get_test_result(test, cwd, test_executable)
                if passed:
                    test_results["FAIL_TO_PASS_POST"]["passed"] += 1
                elif error:
                    raise SampleError(error)
            except SampleError as e:
                test_results["FAIL_TO_PASS_POST"]["errors"].append({"test": test, "error": str(e)})
    print("FAIL_TO_PASS_POST results: ", test_results["FAIL_TO_PASS_POST"])

    return test_results
