import argparse
import glob
import logging
from pathlib import Path
from typing import Optional

from termcolor import cprint

from mentat.parsers.block_parser import BlockParser
from mentat.parsers.file_edit import FileEdit

from .code_context import CodeContext
from .code_file import parse_intervals
from .code_file_manager import CodeFileManager
from .config_manager import ConfigManager, mentat_dir_path
from .conversation import Conversation
from .errors import MentatError, UserError
from .git_handler import get_shared_git_root_for_paths
from .llm_api import CostTracker, setup_api_key
from .logging_config import setup_logging
from .user_input_manager import UserInputManager, UserQuitInterrupt


def run_cli():
    parser = argparse.ArgumentParser(
        description="Run conversation with command line args"
    )
    parser.add_argument(
        "paths",
        nargs="*",
        default=[],
        help="List of file paths, directory paths, or glob patterns",
    )
    parser.add_argument(
        "--exclude",
        "-e",
        nargs="*",
        default=[],
        help="List of file paths, directory paths, or glob patterns to exclude",
    )
    parser.add_argument(
        "--no-code-map",
        action="store_true",
        help="Exclude the file structure/syntax map from the system prompt",
    )
    parser.add_argument(
        "--diff",
        "-d",
        type=str,
        default=None,
        help="A git tree-ish (e.g. commit, branch, tag) to diff against",
    )
    parser.add_argument(
        "--pr-diff",
        "-p",
        type=str,
        default=None,
        help="A git tree-ish to diff against the latest common ancestor of",
    )

    args = parser.parse_args()
    paths = args.paths
    exclude_paths = args.exclude
    no_code_map = args.no_code_map
    diff = args.diff
    pr_diff = args.pr_diff
    # Expanding paths as soon as possible because some shells such as zsh automatically
    # expand globs and we want to avoid differences in functionality between shells
    run(
        expand_paths(paths),
        expand_paths(exclude_paths),
        no_code_map,
        diff,
        pr_diff,
    )


def expand_paths(paths: list[str]) -> list[Path]:
    globbed_paths = set[str]()
    invalid_paths = list[str]()
    for path in paths:
        new_paths = glob.glob(pathname=path, recursive=True)
        if new_paths:
            globbed_paths.update(new_paths)
        else:
            split = path.rsplit(":", 1)
            p = split[0]
            if len(split) > 1:
                # Parse additional syntax, e.g. "path/to/file.py:1-5,7,12-40"
                intervals = parse_intervals(split[1])
            else:
                intervals = None
            if Path(p).exists() and intervals:
                globbed_paths.add(path)
            else:
                invalid_paths.append(path)
    if invalid_paths:
        cprint(
            "The following paths do not exist:",
            "light_yellow",
        )
        print("\n".join(invalid_paths))
        exit()
    return [Path(path) for path in globbed_paths]


def run(
    paths: list[Path],
    exclude_paths: Optional[list[Path]] = None,
    no_code_map: bool = False,
    diff: Optional[str] = None,
    pr_diff: Optional[str] = None,
):
    mentat_dir_path.mkdir(parents=True, exist_ok=True)
    setup_logging()
    logging.debug(f"Paths: {paths}")

    cost_tracker = CostTracker()
    try:
        setup_api_key()
        loop(paths, exclude_paths, cost_tracker, no_code_map, diff, pr_diff)
    except (
        EOFError,
        KeyboardInterrupt,
        UserQuitInterrupt,
        UserError,
        MentatError,
    ) as e:
        if str(e):
            cprint("\n" + str(e), "red")
    finally:
        cost_tracker.display_total_cost()


def loop(
    paths: list[Path],
    exclude_paths: Optional[list[Path]],
    cost_tracker: CostTracker,
    no_code_map: bool,
    diff: Optional[str],
    pr_diff: Optional[str],
) -> None:
    git_root = get_shared_git_root_for_paths([Path(path) for path in paths])
    # The parser can be selected here
    parser = BlockParser()
    config = ConfigManager(git_root)
    code_file_manager = CodeFileManager(config)
    code_context = CodeContext(
        config, paths, exclude_paths or [], diff, pr_diff, no_code_map
    )
    code_context.display_context()
    user_input_manager = UserInputManager(config, code_context)
    conv = Conversation(parser, config, cost_tracker, code_context, code_file_manager)

    cprint("Type 'q' or use Ctrl-C to quit at any time.\n", color="cyan")
    cprint("What can I do for you?", color="light_blue")
    need_user_request = True
    while True:
        if need_user_request:
            user_response = user_input_manager.collect_user_input()
            conv.add_user_message(user_response)

        file_edits = conv.get_model_response(parser, config)
        file_edits = [
            file_edit
            for file_edit in file_edits
            if file_edit.is_valid(code_file_manager, config)
        ]
        if file_edits:
            need_user_request = get_user_feedback_on_edits(
                config,
                conv,
                code_context,
                user_input_manager,
                code_file_manager,
                file_edits,
            )
        else:
            need_user_request = True


def get_user_feedback_on_edits(
    config: ConfigManager,
    conv: Conversation,
    code_context: CodeContext,
    user_input_manager: UserInputManager,
    code_file_manager: CodeFileManager,
    file_edits: list[FileEdit],
) -> bool:
    cprint(
        "Apply these changes? 'Y/n/i' or provide feedback.",
        color="light_blue",
    )
    user_response = user_input_manager.collect_user_input()

    need_user_request = True
    match user_response.lower():
        case "y" | "":
            edits_to_apply = file_edits
            conv.add_user_message("User chose to apply all your changes.")
        case "n":
            edits_to_apply = []
            conv.add_user_message("User chose not to apply any of your changes.")
        case "i":
            edits_to_apply = user_filter_changes(
                code_file_manager, user_input_manager, config, file_edits
            )
            conv.add_user_message(
                "User chose to apply"
                f" {len(edits_to_apply)}/{len(file_edits)} of your suggested"
                " changes."
            )
        case _:
            need_user_request = False
            edits_to_apply = []
            conv.add_user_message(
                "User chose not to apply any of your changes. User response:"
                f" {user_response}\n\nPlease adjust your previous plan and changes to"
                " reflect this. Respond with a full new set of changes."
            )

    for file_edit in edits_to_apply:
        file_edit.resolve_conflicts(user_input_manager)

    if edits_to_apply:
        code_file_manager.write_changes_to_files(
            edits_to_apply, code_context, user_input_manager
        )
        cprint("Changes applied.", color="light_blue")
    else:
        cprint("No changes applied.", color="light_blue")

    if need_user_request:
        cprint("Can I do anything else for you?", color="light_blue")

    return need_user_request


def user_filter_changes(
    code_file_manager: CodeFileManager,
    user_input_manager: UserInputManager,
    config: ConfigManager,
    file_edits: list[FileEdit],
) -> list[FileEdit]:
    new_edits = list[FileEdit]()
    for file_edit in file_edits:
        if file_edit.filter_replacements(code_file_manager, user_input_manager, config):
            new_edits.append(file_edit)

    return new_edits
