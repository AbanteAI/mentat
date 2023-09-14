import argparse
import glob
import logging
from pathlib import Path
from textwrap import dedent
from typing import Optional

from termcolor import cprint

from .code_change import CodeChange, CodeChangeAction
from .code_change_display import print_change
from .code_context import CodeContext
from .code_file import parse_intervals
from .code_file_manager import CodeFileManager
from .code_map import CodeMap
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
    args = parser.parse_args()
    paths = args.paths
    exclude_paths = args.exclude
    no_code_map = args.no_code_map
    # Expanding paths as soon as possible because some shells such as zsh automatically
    # expand globs and we want to avoid differences in functionality between shells
    run(expand_paths(paths), expand_paths(exclude_paths), no_code_map)


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
):
    mentat_dir_path.mkdir(parents=True, exist_ok=True)
    setup_logging()
    logging.debug(f"Paths: {paths}")

    cost_tracker = CostTracker()
    try:
        setup_api_key()
        loop(paths, exclude_paths, cost_tracker, no_code_map)
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
) -> None:
    git_root = get_shared_git_root_for_paths([Path(path) for path in paths])
    config = ConfigManager(git_root)
    code_context = CodeContext(config, paths, exclude_paths or [])
    code_context.display_context()
    user_input_manager = UserInputManager(config, code_context)
    code_file_manager = CodeFileManager(user_input_manager, config, code_context)
    code_map = CodeMap(git_root, token_limit=2048) if not no_code_map else None
    if code_map is not None and code_map.ctags_disabled:
        ctags_disabled_message = f"""
            There was an error with your universal ctags installation, disabling CodeMap.
            Reason: {code_map.ctags_disabled_reason}
        """
        ctags_disabled_message = dedent(ctags_disabled_message)
        cprint(ctags_disabled_message, color="yellow")
    conv = Conversation(config, cost_tracker, code_file_manager, code_map)

    cprint("Type 'q' or use Ctrl-C to quit at any time.\n", color="cyan")
    cprint("What can I do for you?", color="light_blue")
    need_user_request = True
    while True:
        if need_user_request:
            user_response = user_input_manager.collect_user_input()
            conv.add_user_message(user_response)

        _, code_changes = conv.get_model_response(config)

        if code_changes:
            need_user_request = get_user_feedback_on_changes(
                config, conv, user_input_manager, code_file_manager, code_changes
            )
        else:
            need_user_request = True


def get_user_feedback_on_changes(
    config: ConfigManager,
    conv: Conversation,
    user_input_manager: UserInputManager,
    code_file_manager: CodeFileManager,
    code_changes: list[CodeChange],
) -> bool:
    cprint(
        "Apply these changes? 'Y/n/i' or provide feedback.",
        color="light_blue",
    )
    user_response = user_input_manager.collect_user_input()

    need_user_request = True
    match user_response.lower():
        case "y" | "":
            code_changes_to_apply = code_changes
            conv.add_user_message("User chose to apply all your changes.")
        case "n":
            code_changes_to_apply = []
            conv.add_user_message("User chose not to apply any of your changes.")
        case "i":
            code_changes_to_apply, indices = user_filter_changes(
                user_input_manager, code_changes
            )
            conv.add_user_message(
                "User chose to apply"
                f" {len(code_changes_to_apply)}/{len(code_changes)} of your suggest"
                " changes. The changes they applied were:"
                f" {', '.join(map(str, indices))}"
            )
        case _:
            need_user_request = False
            code_changes_to_apply = []
            conv.add_user_message(
                "User chose not to apply any of your changes. User response:"
                f" {user_response}\n\nPlease adjust your previous plan and changes to"
                " reflect this. Respond with a full new set of changes."
            )

    if code_changes_to_apply:
        code_file_manager.write_changes_to_files(code_changes_to_apply)
        if len(code_changes_to_apply) == len(code_changes):
            cprint("Changes applied.", color="light_blue")
        else:
            cprint("Selected changes applied.", color="light_blue")
    else:
        cprint("No changes applied.", color="light_blue")

    if need_user_request:
        cprint("Can I do anything else for you?", color="light_blue")

    return need_user_request


def user_filter_changes(
    user_input_manager: UserInputManager, code_changes: list[CodeChange]
) -> tuple[list[CodeChange], list[int]]:
    new_changes = list[CodeChange]()
    indices = list[int]()
    for index, change in enumerate(code_changes, start=1):
        print_change(change)
        # Allowing the user to remove rename file changes introduces a lot of edge cases
        if change.action == CodeChangeAction.RenameFile:
            new_changes.append(change)
            indices.append(index)
            cprint("Cannot remove rename file change", "light_yellow")
            continue

        cprint("Keep this change?", "light_blue")
        if user_input_manager.ask_yes_no(default_yes=True):
            new_changes.append(change)
            indices.append(index)

    return new_changes, indices
