import argparse
import glob
import logging
from typing import Iterable, Optional

from .code_change import CodeChange
from .code_change_display import print_change
from .code_file_manager import CodeFileManager
from .config_manager import ConfigManager, mentat_dir_path
from .conversation import Conversation
from .errors import MentatError, UserError
from .git_handler import get_shared_git_root_for_paths
from .interface import InterfaceType, MentatInterface, initialize_mentat_interface
from .llm_api import CostTracker, setup_api_key
from .logging_config import setup_logging
from .user_input_manager import UserQuitInterrupt


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
        "--interface",
        "-i",
        choices=[InterfaceType.Terminal, InterfaceType.VSCode],
        default=InterfaceType.Terminal,
        help="Interface type",
    )
    args = parser.parse_args()
    paths = args.paths
    exclude_paths = args.exclude
    interface_type = args.interface

    interface = initialize_mentat_interface(interface_type)

    run(
        interface, 
        expand_paths(interface, paths), 
        expand_paths(interface, exclude_paths)
    )


def expand_paths(
    interface: MentatInterface, 
    paths: Iterable[str]
) -> Iterable[str]:
    globbed_paths = set()
    invalid_paths = []
    for path in paths:
        new_paths = glob.glob(pathname=path, recursive=True)
        if new_paths:
            globbed_paths.update(new_paths)
        else:
            invalid_paths.append(path)
    if invalid_paths:
        interface.display(
            "The following paths do not exist:",
            "light_yellow",
        )
        interface.display("\n".join(invalid_paths))
        interface.exit()
    return globbed_paths


def run(
    interface: MentatInterface,
    paths: Iterable[str], 
    exclude_paths: Optional[Iterable[str]] = None
):
    mentat_dir_path.mkdir(parents=True, exist_ok=True)
    setup_logging()
    logging.debug(f"Paths: {paths}")

    cost_tracker = CostTracker()
    try:
        setup_api_key()
        loop(interface, paths, exclude_paths, cost_tracker)
    except (
        EOFError,
        KeyboardInterrupt,
        UserQuitInterrupt,
        UserError,
        MentatError,
    ) as e:
        if str(e):
            interface.display("\n" + str(e), "red")
    finally:
        cost_tracker.display_total_cost(interface)


def loop(
    interface: MentatInterface,
    paths: Iterable[str],
    exclude_paths: Optional[Iterable[str]],
    cost_tracker: CostTracker,
) -> None:
    git_root = get_shared_git_root_for_paths(paths)
    config = ConfigManager(git_root, interface)
    interface.register_config(config)
    code_file_manager = CodeFileManager(
        interface,
        paths,
        exclude_paths if exclude_paths is not None else [],
        config,
        git_root,
    )
    conv = Conversation(interface, config, cost_tracker, code_file_manager)

    interface.display("Type 'q' or use Ctrl-C to quit at any time.\n", "cyan")
    interface.display("What can I do for you?", color="light_blue")
    need_user_request = True
    while True:
        if need_user_request:
            user_response = interface.get_user_input()
            conv.add_user_message(user_response)
        explanation, code_changes = conv.get_model_response(config)

        if code_changes:
            need_user_request = get_user_feedback_on_changes(
                interface, config, conv, code_file_manager, code_changes
            )
        else:
            need_user_request = True


def get_user_feedback_on_changes(
    interface: MentatInterface,
    config: ConfigManager,
    conv: Conversation,
    code_file_manager: CodeFileManager,
    code_changes: Iterable[CodeChange],
) -> bool:
    interface.display(
        "Apply these changes? 'Y/n/i' or provide feedback.",
        color="light_blue",
    )
    user_response = interface.get_user_input(options=['y', 'n', 'i'])

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
                interface, code_changes
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
            interface.display("Changes applied.", color="light_blue")
        else:
            interface.display("Selected changes applied.", color="light_blue")
    else:
        interface.display("No changes applied.", color="light_blue")

    if need_user_request:
        interface.display("Can I do anything else for you?", color="light_blue")

    return need_user_request


def user_filter_changes(
    interface: MentatInterface, code_changes: Iterable[CodeChange]
) -> Iterable[CodeChange]:
    new_changes = []
    indices = []
    for index, change in enumerate(code_changes, start=1):
        print_change(change)
        interface.display("Keep this change?", "light_blue")
        if interface.ask_yes_no(default_yes=True):
            new_changes.append(change)
            indices.append(index)
    return new_changes, indices
