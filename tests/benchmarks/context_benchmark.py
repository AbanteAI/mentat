"""
Given a codebase, a prompt and a token limit, code_context will auto-select
features to include in the code_message. This script evaluates the 
performance of that selection algorithm.

Test Guidelines:
- Codebase should be larger than the token limit
- Prompts should be thorough and specific - give it the best chance to succeed
- Tasks should draw on multiple files/features.

Scoring:
- Score based on the features (path, level, diff) auto-selected
- Use traditional precision, recall and f1 scores:
    - y_pred = [(f in code_context.features) for f in all_features]
    - y_true = [(f in test.expected) for f in all_features]

Fine-tuning:
An auto-context process might look like this:
1. Use local methods (embeddings) to select a full-context worth
    of features
2. Send the code_message of those features to gpt-3, and have it 
    return a modified features spec [(path, level, diff)] based on what's
    relevant and not. (Bonus: let gpt-3 ask for more info if it needs it)
3. Use the modified features to get_code_message for gpt-4

These tests can be used to train/score #1 or #2, but we'd expect #2 to score 
a lot higher.
"""
import os
import subprocess
from pathlib import Path

import pytest

from mentat.code_context import CodeContext, CodeContextSettings
from mentat.code_feature import CodeFeature, CodeMessageLevel
from mentat.git_handler import get_non_gitignored_files
from mentat.llm_api import setup_api_key
from tests.benchmarks.utils import clone_repo

pytestmark = pytest.mark.benchmark

tests = [
    {
        "name": "Mentat: replace subprocess/git with GitPython",
        "codebase_url": "http://github.com/AbanteAI/mentat",
        "codebase_name": "mentat",
        "commit": "a9f055e",
        "args": {"paths": ["mentat/__init__.py"]},
        "prompt": (
            "I want to update all the files in git_handler to use the 'Repo' class from"
            " GitPython instead of calling subprocess. Update each function in"
            " mentat/git_handler.py that calls subprocess to use Repo instead. If git"
            " is run with subprocess anywhere in the code, update those as well."
        ),
        "expected_features": [
            "mentat/git_handler.py",
            "mentat/diff_context.py:173-179",
            "tests/benchmark_test.py:118-139",
            "tests/commands_test.py:26-34",
            "tests/conftest.py:259-266",
            "tests/diff_context_test.py",
            "tests/git_handler_test.py:23-30",
            "tests/clients/terminal_client_test.py:62-93",
        ],
        "expected_edits": [
            # for other benchmarks
        ],
    },
    {
        "name": "simoc-abm: Change 'Lamp' to 'Electric Light'",
        "codebase_url": "http://github.com/overthesun/simoc-abm",
        "codebase_name": "simoc-abm",
        "commit": "d77f44f",
        "args": {"ignore_paths": ["src/simoc_abm/data_files", "test/*"]},
        "prompt": (
            "Rename 'lamp' to 'electric light' throughout the code. Update "
            "instances of 'lamp' to 'electric_light', and 'Lamp' to 'Electric "
            "Light', and if there's a class Lamp, should be class ElectricLight."
        ),
        "expected_features": [
            "docs/api.rst:21-22",
            "src/simoc_abm/agent_model.py:129-230",
            "src/simoc_abm/agents/__init__.py",
            "src/simoc_abm/agents/lamp.py",
            "src/simoc_abm/agents/plant.py:135-197",
        ],
        "expected_edits": [],
    },
    {
        "name": "mentat: add warnings when include/exclude paths are invalid",
        "codebase_url": "http://github.com/AbanteAI/mentat",
        "codebase_name": "mentat",
        "commit": "9ce6d78abf65725b2341d3c399184b1584e4bc20",
        "args": {},
        "prompt": (
            "Improve handling of warnings for include and exclude commands for"
            " text-encoded files and invalid paths."
        ),
        "expected_edits": (
            "1. Modify the expand_paths function to return a tuple of valid paths and"
            " invalid paths.\n2. Update the get_include_files function to handle"
            " invalid_paths returned from expand_paths.\n3. Add a new function"
            " print_invalid_path to handle different cases of invalid paths and print"
            " appropriate warnings.\n4. Update the create method in CodeContext class"
            " to use print_invalid_path function.\n5. Update the include_file and"
            " exclude_file methods in CodeContext class to return included/excluded"
            " paths along with invalid paths.\n6. Modify the IncludeCommand and"
            " ExcludeCommand classes to handle and display the invalid paths and"
            " added/removed paths using the new print_invalid_path function.\n\n@"
            " mentat/code_context.py starting_line=22 ending_line=20\n   "
            " print_invalid_path,\n@\n@ mentat/code_context.py starting_line=58"
            " ending_line=58\n@\n@ mentat/code_context.py starting_line=67"
            " ending_line=69\n            await print_invalid_path(invalid_path)\n@\n@"
            " mentat/code_context.py starting_line=316 ending_line=321\n        return"
            " list(paths.keys()), invalid_paths\n\n    def exclude_file(self, path:"
            " Path):\n        # TODO: Using get_include_files here isn't ideal; if the"
            " user puts in a glob that\n        # matches files but doesn't match any"
            " files in context, we won't know what that glob is\n        # and can't"
            " return it as an invalid path\n        paths, invalid_paths ="
            " get_include_files([path], [])\n        removed_paths = list[Path]()\n    "
            "    for new_path in paths.keys():\n            if new_path in"
            " self.include_files:\n                removed_paths.append(new_path)\n    "
            "            del self.include_files[new_path]\n        return"
            " removed_paths, invalid_paths\n@\n@ mentat/commands.py starting_line=11"
            " ending_line=15\nfrom mentat.include_files import print_invalid_path\nfrom"
            " mentat.session_stream import SESSION_STREAM\nfrom mentat.utils import"
            " create_viewer\n\nfrom .code_context import CODE_CONTEXT\nfrom .errors"
            " import MentatError\nfrom .git_handler import GIT_ROOT, commit\n@\n@"
            " mentat/commands.py starting_line=143 ending_line=154\n        git_root ="
            " GIT_ROOT.get()\n\n        if len(args) == 0:\n            await"
            ' stream.send("No files specified\\n", color="yellow")\n           '
            " return\n        for file_path in args:\n            included_paths,"
            " invalid_paths = code_context.include_file(\n               "
            " Path(file_path).absolute()\n            )\n            for invalid_path"
            " in invalid_paths:\n                await"
            " print_invalid_path(invalid_path)\n            for included_path in"
            " included_paths:\n                rel_path ="
            " included_path.relative_to(git_root)\n                await"
            ' stream.send(f"{rel_path} added to context", color="green")\n@\n@'
            " mentat/commands.py starting_line=170 ending_line=175\n        git_root ="
            " GIT_ROOT.get()\n\n        if len(args) == 0:\n            await"
            ' stream.send("No files specified\\n", color="yellow")\n           '
            " return\n        for file_path in args:\n            excluded_paths,"
            " invalid_paths = code_context.exclude_file(\n               "
            " Path(file_path).absolute()\n            )\n            for invalid_path"
            " in invalid_paths:\n                await"
            " print_invalid_path(invalid_path)\n            for excluded_path in"
            " excluded_paths:\n                rel_path ="
            " excluded_path.relative_to(git_root)\n                await"
            ' stream.send(f"{rel_path} removed from context", color="red")\n@\n@'
            " mentat/include_files.py insert_line=14\ndef expand_paths(paths:"
            " list[Path]) -> tuple[list[Path], list[str]]:\n@\n@"
            " mentat/include_files.py insert_line=33\n    return [Path(path).resolve()"
            " for path in globbed_paths], list(invalid_paths)\n@\n@"
            " mentat/include_files.py starting_line=87 ending_line=87\n    paths,"
            " invalid_paths = expand_paths(paths)\n    exclude_paths, _ ="
            " expand_paths(exclude_paths)\n@\n@ mentat/include_files.py"
            " starting_line=107 ending_line=108\n    files_direct, files_from_dirs,"
            " non_text_paths = abs_files_from_list(\n        paths,"
            " check_for_text=True\n    )\n   "
            " invalid_paths.extend(non_text_paths)\n@\n@ mentat/include_files.py"
            " starting_line=166 ending_line=164\n\n\nasync def"
            " print_invalid_path(invalid_path: str):\n    stream ="
            " SESSION_STREAM.get()\n    git_root = GIT_ROOT.get()\n\n    abs_path ="
            ' Path(invalid_path).absolute()\n    if "*" in invalid_path:\n        await'
            ' stream.send(\n            f"The glob pattern {invalid_path} did not match'
            ' any files",\n            color="light_red",\n        )\n    elif not'
            ' abs_path.exists():\n        await stream.send(\n            f"The path'
            ' {invalid_path} does not exist and was skipped", color="light_red"\n      '
            "  )\n    elif not is_file_text_encoded(abs_path):\n        rel_path ="
            " abs_path.relative_to(git_root)\n        await stream.send(\n           "
            ' f"The file {rel_path} is not text encoded and was skipped",\n           '
            ' color="light_red",\n        )\n    else:\n        await stream.send(f"The'
            ' file {invalid_path} was skipped", color="light_red")\n@\n'
        ),
        "expected_features": [
            "mentat/code_context.py:21-321",
            "mentat/commands.py:10-175",
            "mentat/include_files.py:13-164",
        ],
    },
]


def matches(test, name):
    prefix_length = min(len(test["commit"]), len(name))
    if test["commit"][:prefix_length] == name[:prefix_length]:
        return True
    if name in test["name"]:
        return True
    return False


@pytest.mark.asyncio
async def test_code_context_performance(
    mock_session_context, benchmarks, max_benchmarks
):
    setup_api_key()

    if len(benchmarks) > 0:
        tests_to_run = []
        for test in tests:
            for benchmark in benchmarks:
                if matches(test, benchmark):
                    tests_to_run.append(test)
                    break
    else:
        tests_to_run = tests[:max_benchmarks]

    for test in tests_to_run:
        print(f"\n\n{test['name']}\n{test['prompt']}")

        code_dir = clone_repo(test["codebase_url"], test["codebase_name"])
        os.chdir(code_dir)
        if test["commit"]:
            subprocess.run(
                ["git", "checkout", test["commit"]],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        mock_session_context.git_root = code_dir

        paths = test["args"].get("paths", [])
        exclude_paths = test["args"].get("exclude_paths", [])
        ignore_paths = test["args"].get("ignore_paths", [])
        rest = {
            k: v
            for k, v in test["args"].items()
            if k not in ["paths", "exclude_paths", "ignore_paths"]
        }
        settings = CodeContextSettings(
            use_embeddings=True,
            auto_tokens=7000,
            **rest,
        )
        code_context = CodeContext(
            stream=mock_session_context.stream,
            git_root=code_dir,
            settings=settings,
        )
        code_context.set_paths(paths, exclude_paths, ignore_paths)
        _ = await code_context.get_code_message(test["prompt"], "gpt-4", 7000)

        # Calculate y_pred and y_true
        actual = {
            f.path for f in code_context.features if f.level == CodeMessageLevel.CODE
        }
        expected_features = {
            CodeFeature(f).path for f in test["expected_features"]
        }  # Ignore line numbers for now
        all_files = [Path(f) for f in get_non_gitignored_files(code_dir)]
        y_pred = [f in actual for f in all_files]
        y_true = [f in expected_features for f in all_files]

        _TP = sum([1 for p, t in zip(y_pred, y_true) if p and t])
        _TN = sum([1 for p, t in zip(y_pred, y_true) if not p and not t])
        _FP = sum([1 for p, t in zip(y_pred, y_true) if p and not t])
        _FN = sum([1 for p, t in zip(y_pred, y_true) if not p and t])
        print(f"True Positive:\t{_TP:.3f}")
        print(f"True Negative:\t{_TN:.3f}")
        print(f"False Positive:\t{_FP:.3f}")
        print(f"False Negative:\t{_FN:.3f}")

        precision, recall = None, None
        if (_TP + _FP) > 0:
            precision = _TP / (_TP + _FP)
            print(
                f"Precision:\t{precision:.3f}\t| How many selected features are"
                " relevant?"
            )
        if (_TP + _FN) > 0:
            recall = _TP / (_TP + _FN)
            print(
                f"Recall:\t\t{recall:.3f}\t| How many relevant features are selected?"
            )
        if precision and recall:
            f1 = 2 * precision * recall / (precision + recall)
            print(f"F1:\t\t{f1:.3f}\t| Weighted average of precision and recall")
