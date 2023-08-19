import argparse
import glob
import logging
from typing import Iterable, Optional

from termcolor import cprint

from .code_change import CodeChange
from .code_change_display import print_change
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
    args = parser.parse_args()
    paths = args.paths
    exclude_paths = args.exclude
    run(expand_paths(paths), expand_paths(exclude_paths))


def expand_paths(paths: Iterable[str]) -> Iterable[str]:
    globbed_paths = set()
    invalid_paths = []
    for path in paths:
        new_paths = glob.glob(pathname=path, recursive=True)
        if new_paths:
            globbed_paths.update(new_paths)
        else:
            invalid_paths.append(path)
    if invalid_paths:
        cprint(
            "The following paths do not exist:",
            "light_yellow",
        )
        print("\n".join(invalid_paths))
        exit()
    return globbed_paths


def run(paths: Iterable[str], exclude_paths: Optional[Iterable[str]] = None):
    mentat_dir_path.mkdir(parents=True, exist_ok=True)
    setup_logging()
    logging.debug(f"Paths: {paths}")

    cost_tracker = CostTracker()
    try:
        setup_api_key()
        loop(paths, exclude_paths, cost_tracker)
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
    paths: Iterable[str],
    exclude_paths: Optional[Iterable[str]],
    cost_tracker: CostTracker,
) -> None:
    git_root = get_shared_git_root_for_paths(paths)
    config = ConfigManager(git_root)
    user_input_manager = UserInputManager(config)
    code_file_manager = CodeFileManager(
        paths,
        exclude_paths if exclude_paths is not None else [],
        user_input_manager,
        config,
        git_root,
    )
    conv = Conversation(config, cost_tracker, code_file_manager)

    cprint("Type 'q' or use Ctrl-C to quit at any time.\n", color="cyan")
    cprint("What can I do for you?", color="light_blue")
    need_user_request = True
    while True:
        if need_user_request:
            user_response = user_input_manager.collect_user_input()
            conv.add_user_message(user_response)
        explanation, code_changes = conv.get_model_response(config)

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
    code_changes: Iterable[CodeChange],
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
    user_input_manager: UserInputManager, code_changes: Iterable[CodeChange]
) -> Iterable[CodeChange]:
    new_changes = []
    indices = []
    for index, change in enumerate(code_changes, start=1):
        print_change(change)
        cprint("Keep this change?", "light_blue")
        if user_input_manager.ask_yes_no(default_yes=True):
            new_changes.append(change)
            indices.append(index)
    return new_changes, indices
