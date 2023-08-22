# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
"""Implementation of tool support over LSP."""
from __future__ import annotations

import os
import sys
import json
import pathlib
import zipfile
import asyncio
import platform
from typing import Any, Optional, Sequence


# **********************************************************
# Update sys.path before importing any bundled libraries.
# **********************************************************
def update_sys_path(path_to_add: str, strategy: str) -> None:
    """Add given path to `sys.path`."""
    if path_to_add not in sys.path and os.path.isdir(path_to_add):
        if strategy == "useBundled":
            sys.path.insert(0, path_to_add)
        elif strategy == "fromEnvironment":
            sys.path.append(path_to_add)


# Ensure that we can import LSP libraries, and other bundled libraries.
update_sys_path(
    os.fspath(pathlib.Path(__file__).parent.parent / "libs"),
    "useBundled",  # This was required to import mentat
    # os.getenv("LS_IMPORT_STRATEGY", "useBundled"),
)


# Install the architecture-specific version of tiktoken from bundled wheel
tiktoken_path = os.fspath(pathlib.Path(__file__).parent.parent / "libs" / "tiktoken")
if not os.path.isdir(tiktoken_path):

    # Select Python version
    wheels_path = pathlib.Path(__file__).parent.parent / "libs" / "tiktoken_wheels"
    available_wheels = [wheel.name for wheel in wheels_path.iterdir()]
    latest_py_version = max([int(wheel.split('-')[2][2:]) for wheel in available_wheels])
    user_py_version = int(f'{sys.version_info.major}{sys.version_info.minor}')
    py_version = str(min(latest_py_version, int(user_py_version)))

    # Select architecture
    system = platform.system()
    arch = platform.machine()
    SYSTEM_ARCH_MAPPING = {
        ('Windows', 'x86_64'): ('win', 'amd64'),
        ('Linux', 'x86_64'): ('manylinux2014', 'x86_64'),
        ('Linux', 'aarch64'): ('musllinux_1_1', 'aarch64'),
        ('Darwin', 'x86_64'): ('macosx_10_9', 'x86_64'),
        ('Darwin', 'arm64'): ('macosx_11_0', 'arm64'),
    }
    try:
        system, arch = SYSTEM_ARCH_MAPPING[(system, arch)]
    except KeyError:
        raise Exception("Unsupported system or architecture")
    
    # Find the wheel
    pattern = f"tiktoken-*-cp{py_version}-cp{py_version}-{system}_{arch}.whl"
    matching_wheels = list(wheels_path.glob(pattern))
    if len(matching_wheels) == 0:
        raise Exception(f"Compatible wheel for tiktoken not found for {system} on {arch} using Python {py_version}")

    # Install the wheel
    os.mkdir(tiktoken_path)
    with zipfile.ZipFile(matching_wheels[0], 'r') as zip_ref:
        zip_ref.extractall(path=str(tiktoken_path))


# **********************************************************
# Imports needed for the language server goes below this.
# **********************************************************
# pylint: disable=wrong-import-position,import-error
import lsp_jsonrpc as jsonrpc
import lsp_utils as utils
import lsprotocol.types as lsp
from pygls import server, uris, workspace

WORKSPACE_SETTINGS = {}
GLOBAL_SETTINGS = {}
RUNNER = pathlib.Path(__file__).parent / "lsp_runner.py"

MAX_WORKERS = 5
# TODO: Update the language server name and version.
LSP_SERVER = server.LanguageServer(
    name="Mentat", version="<server version>", max_workers=MAX_WORKERS
)


# **********************************************************
# Mentat features
# **********************************************************

dev_mode = os.environ.get('USE_DEBUGPY')  # TODO: Not the best flag?
if dev_mode:
  # For local development, add the path to local installation of mentat.
  mentat_inner_path = pathlib.Path(__file__).parent.parent.parent.parent
  sys.path.insert(0, str(mentat_inner_path))

from mentat.mentat_runner import MentatRunner

_MR = None

@LSP_SERVER.command('mentat.getResponse')
async def handle_mentat_get_response(data: str):
    global _MR
    def stream_response(chunk):
        LSP_SERVER.send_notification('mentat.sendChunk', chunk)
    asyncio.create_task(_MR.get_response(data, stream_response))
    return 

@LSP_SERVER.command('mentat.interrupt')
def handle_mentat_interrupt(data: str):
    global _MR
    return _MR.interrupt()

@LSP_SERVER.command('mentat.restart')
async def handle_mentat_restart(data: list):
    global _MR
    if _MR is not None:
        _MR.cleanup()
    _MR = MentatRunner(data)
    response = f'Mentat initialized with paths={str(_MR.paths)} exclude={str(_MR.exclude_paths)}'
    async def echo():
        await asyncio.sleep(0.5)
        LSP_SERVER.send_notification('mentat.sendChunk', response)
    asyncio.create_task(echo())

# **********************************************************
# Required Language Server Initialization and Exit handlers.
# **********************************************************
@LSP_SERVER.feature(lsp.INITIALIZE)
def initialize(params: lsp.InitializeParams) -> None:
    """LSP handler for initialize request."""
    log_to_output(f"CWD Server: {os.getcwd()}")

    paths = "\r\n   ".join(sys.path)
    log_to_output(f"sys.path used to run Server:\r\n   {paths}")

    GLOBAL_SETTINGS.update(**params.initialization_options.get("globalSettings", {}))

    settings = params.initialization_options["settings"]
    _update_workspace_settings(settings)
    log_to_output(
        f"Settings used to run Server:\r\n{json.dumps(settings, indent=4, ensure_ascii=False)}\r\n"
    )
    log_to_output(
        f"Global settings:\r\n{json.dumps(GLOBAL_SETTINGS, indent=4, ensure_ascii=False)}\r\n"
    )


@LSP_SERVER.feature(lsp.EXIT)
def on_exit(_params: Optional[Any] = None) -> None:
    """Handle clean up on exit."""
    jsonrpc.shutdown_json_rpc()


@LSP_SERVER.feature(lsp.SHUTDOWN)
def on_shutdown(_params: Optional[Any] = None) -> None:
    """Handle clean up on shutdown."""
    jsonrpc.shutdown_json_rpc()


def _get_global_defaults():
    return {
        "path": GLOBAL_SETTINGS.get("path", []),
        "interpreter": GLOBAL_SETTINGS.get("interpreter", [sys.executable]),
        "args": GLOBAL_SETTINGS.get("args", []),
        "importStrategy": GLOBAL_SETTINGS.get("importStrategy", "useBundled"),
        "showNotifications": GLOBAL_SETTINGS.get("showNotifications", "off"),
    }


def _update_workspace_settings(settings):
    if not settings:
        key = os.getcwd()
        WORKSPACE_SETTINGS[key] = {
            "cwd": key,
            "workspaceFS": key,
            "workspace": uris.from_fs_path(key),
            **_get_global_defaults(),
        }
        return

    for setting in settings:
        key = uris.to_fs_path(setting["workspace"])
        WORKSPACE_SETTINGS[key] = {
            **setting,
            "workspaceFS": key,
        }


def _get_settings_by_path(file_path: pathlib.Path):
    workspaces = {s["workspaceFS"] for s in WORKSPACE_SETTINGS.values()}

    while file_path != file_path.parent:
        str_file_path = str(file_path)
        if str_file_path in workspaces:
            return WORKSPACE_SETTINGS[str_file_path]
        file_path = file_path.parent

    setting_values = list(WORKSPACE_SETTINGS.values())
    return setting_values[0]


def _get_document_key(document: workspace.Document):
    if WORKSPACE_SETTINGS:
        document_workspace = pathlib.Path(document.path)
        workspaces = {s["workspaceFS"] for s in WORKSPACE_SETTINGS.values()}

        # Find workspace settings for the given file.
        while document_workspace != document_workspace.parent:
            if str(document_workspace) in workspaces:
                return str(document_workspace)
            document_workspace = document_workspace.parent

    return None


def _get_settings_by_document(document: workspace.Document | None):
    if document is None or document.path is None:
        return list(WORKSPACE_SETTINGS.values())[0]

    key = _get_document_key(document)
    if key is None:
        # This is either a non-workspace file or there is no workspace.
        key = os.fspath(pathlib.Path(document.path).parent)
        return {
            "cwd": key,
            "workspaceFS": key,
            "workspace": uris.from_fs_path(key),
            **_get_global_defaults(),
        }

    return WORKSPACE_SETTINGS[str(key)]


# *****************************************************
# Logging and notification.
# *****************************************************
def log_to_output(
    message: str, msg_type: lsp.MessageType = lsp.MessageType.Log
) -> None:
    LSP_SERVER.show_message_log(message, msg_type)


def log_error(message: str) -> None:
    LSP_SERVER.show_message_log(message, lsp.MessageType.Error)
    if os.getenv("LS_SHOW_NOTIFICATION", "off") in ["onError", "onWarning", "always"]:
        LSP_SERVER.show_message(message, lsp.MessageType.Error)


def log_warning(message: str) -> None:
    LSP_SERVER.show_message_log(message, lsp.MessageType.Warning)
    if os.getenv("LS_SHOW_NOTIFICATION", "off") in ["onWarning", "always"]:
        LSP_SERVER.show_message(message, lsp.MessageType.Warning)


def log_always(message: str) -> None:
    LSP_SERVER.show_message_log(message, lsp.MessageType.Info)
    if os.getenv("LS_SHOW_NOTIFICATION", "off") in ["always"]:
        LSP_SERVER.show_message(message, lsp.MessageType.Info)


# *****************************************************
# Start the server.
# *****************************************************
if __name__ == "__main__":
    LSP_SERVER.start_io()
