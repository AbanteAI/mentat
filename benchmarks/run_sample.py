import json
import subprocess
import re
from pathlib import Path
from typing import Any

from mentat import Mentat
from mentat.errors import SampleError
from mentat.git_handler import get_git_diff
from mentat.parsers.git_parser import GitParser
from mentat.sampler.sample import Sample
from mentat.sampler.utils import get_active_snapshot_commit, setup_repo, apply_diff_to_repo
from mentat.session_context import SESSION_CONTEXT
from mentat.utils import convert_string_to_asynciter


async def run_sample(sample: Sample, cwd: Path | str | None = None) -> dict[str, Any]:
    """Run a sample using Mentat and return the resulting diff"""

    repo = setup_repo(
        url=sample.repo,
        cwd=cwd,
        commit=sample.merge_base,
        diff_merge_base=sample.diff_merge_base,
        diff_active=sample.diff_active,
    )
    cwd = Path(repo.working_dir)

    # Make a commit from the pre-edited state (should match diff_active)
    commit_active = get_active_snapshot_commit(repo)

    # Run the PASS_TO_PASS test to confirm correct setup
    test_results = {
        "FAIL_TO_PASS": {"passed": 0, "total": 0},
        "PASS_TO_PASS": {"passed": 0, "total": 0},
    }
    if sample.PASS_TO_PASS:
        tests = json.loads(sample.PASS_TO_PASS)
        for test in tests:
            passed, error = get_test_result(test, cwd)
            test_results["PASS_TO_PASS"]["total"] += 1
            if passed:
                test_results["PASS_TO_PASS"]["passed"] += 1
            if error:
                print(f"Error running PASS_TO_PASS test '{test}': {error}")

    # Run sample in PythonClient
    paths = list[Path]()
    for a in sample.context:
        paths.append(Path(a))
    mentat = Mentat(cwd=cwd, paths=paths)
    await mentat.startup()
    session_context = SESSION_CONTEXT.get()
    conversation = session_context.conversation
    cost_tracker = session_context.cost_tracker
    for msg in sample.message_history:
        if msg["role"] == "user":
            conversation.add_user_message(msg["content"])
        elif msg["role"] == "assistant":
            generator = convert_string_to_asynciter(msg["content"], 100)
            parsed_llm_response = await GitParser().stream_and_parse_llm_response(generator)
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

    if sample.test_patch:
        apply_diff_to_repo(sample.test_patch, repo)
    if sample.FAIL_TO_PASS:
        tests = json.loads(sample.FAIL_TO_PASS)
        for test in tests:
            passed, error = get_test_result(test, cwd)
            test_results["FAIL_TO_PASS"]["total"] += 1
            if passed:
                test_results["FAIL_TO_PASS"]["passed"] += 1
            if error:
                print(f"Error running FAIL_TO_PASS test '{test}': {error}")

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
        "test_results": test_results,
    }


def get_test_result(test: str, cwd: Path) -> tuple[bool, str]:
    passed, error = False, ""
    try:
        output = subprocess.run(
            test,
            shell=True,
            capture_output=True,
            text=True,
            cwd=cwd,
        )
        if output.returncode != 0:
            raise SampleError(f"Test command failed: {output.stderr}")
        matches = re.search(r"(?:(\d+) passed)?(?:, )?(?:(\d+) failed)?", output.stdout)
        if not matches:
            raise SampleError(f"Failed parsing test result from output: {output.stdout}")
        _passed = int(matches.group(1)) or 0
        _failed = int(matches.group(2)) or 0
        if _passed + _failed != 1:
            raise SampleError(f"Invalid test output: {output.stdout}")
        passed = _passed == 1
    except Exception as e:
        error = str(e)
    return passed, error
