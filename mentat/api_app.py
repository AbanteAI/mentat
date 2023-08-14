import subprocess
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from typing import Set

from .api_image_gen import generate_path_tree_image, generate_code_change_image_and_lines
from .prompts import api_system_prompt
from .code_change import CodeChange
from .code_file_manager import CodeFileManager
from .config_manager import ConfigManager
from .git_handler import get_shared_git_root_for_paths


app = Flask(__name__, static_folder="static")
CORS(app)

state = {
    "available_paths": None,
    "paths": None,
    "exclude_paths": None,
    "git_root": None,
    "config": None,
    "code_file_manager": None,
    "staged_changes": None,
    "focused_paths": set(),
}


def run_api(paths: Set[str], exclude: Set[str]):
    state["paths"] = paths
    state["exclude_paths"] = exclude
    state["available_paths"] = (
        state["paths"] - state["exclude_paths"]
        if state["paths"] and state["exclude_paths"]
        else state["paths"]
    )
    configure_app_state()
    app.run(debug=True, port=3333)


def configure_app_state():
    git_root = get_shared_git_root_for_paths(
        state["focused_paths"] if state["focused_paths"] else state["paths"]
    )
    config = ConfigManager(git_root)
    code_file_manager = CodeFileManager(
        state["focused_paths"] if state["focused_paths"] else [],
        state["exclude_paths"] if state["exclude_paths"] else [],
        None,
        config,
        git_root,
    )
    state.update(
        {
            "git_root": git_root,
            "config": config,
            "code_file_manager": code_file_manager,
        }
    )
    code_file_manager.get_code_message()


@app.route("/focus-on-paths", methods=["POST"])
def focus_on_paths():
    requested_paths: Set[str] = set(request.json.get("paths", []))
    invalid_paths = requested_paths - state["available_paths"]
    if invalid_paths:
        return (
            jsonify(
                {
                    "error": "Invalid paths provided. Provided paths must be within the set of all paths (see /get-all-paths).",
                    "invalid_paths": list(invalid_paths),
                }
            ),
            400,
        )
    state["focused_paths"] = requested_paths
    state["staged_changes"] = None
    configure_app_state()
    return jsonify({"success": True})


@app.route("/get-focused-paths", methods=["GET"])
def get_focused_paths():
    return jsonify(
        {
            "paths": list(state["focused_paths"]),
            "user_output_image": generate_path_tree_image(
                state["focused_paths"], state["git_root"]
            )
            if state["focused_paths"]
            else None,
        }
    )


@app.route("/get-all-paths", methods=["GET"])
def get_all_paths():
    return {
        "paths": sorted(list(state["available_paths"])),
        "user_output_image": generate_path_tree_image(
            state["available_paths"], state["git_root"]
        ),
    }


@app.route("/get-repository-state", methods=["GET"])
def get_repository_state():
    code_message = state["code_file_manager"].get_code_message()
    response = {"code_message": code_message}
    if state["staged_changes"]:
        image_url, code_change_lines = generate_code_change_image_and_lines(
            state["staged_changes"].get("code_changes", [])
        )
        response["staged_changes"] = {
            "summary": state["staged_changes"].get("summary", ""),
            "code_changes": code_change_lines,
            "user_output_image": image_url,
        }
    return response


@app.route("/confirm-or-clear-staged-change", methods=["POST"])
def confirm_or_clear_staged_change():
    accept: bool | None = request.json.get("accept")
    clear: bool | None = request.json.get("clear")
    if accept and state["staged_changes"]:
        state["code_file_manager"].write_changes_to_files(
            state["staged_changes"].get("code_changes", [])
        )
        state["staged_changes"] = None
        return {"applied": True}
    elif clear:
        state["staged_changes"] = None
        return {"cleared": True}


@app.route("/stage-change", methods=["POST"])
def stage_change():
    code_changes = [
        CodeChange(
            code_change,
            code_change.get("code_lines", []),
            state["git_root"],
            state["code_file_manager"],
        )
        for code_change in request.json.get("code_changes")
    ]
    state["staged_changes"] = {
        "summary": request.json.get("summary"),
        "code_changes": code_changes,
    }
    image_url, code_change_lines = generate_code_change_image_and_lines(code_changes)
    response = {
        "staged_changes": code_change_lines,
        "message": "Please confirm or clear the staged changes.",
        "user_output_image": image_url,
    }
    return jsonify(response)


@app.route("/execute-command", methods=["POST"])
def execute_command():
    if not state["config"].api_allow_commands():
        return (
            jsonify({"error": "Commands are not allowed. Must enable in config."}),
            403,
        )
    command = request.json.get("command")
    result = subprocess.run(
        command.split(),
        cwd=state["git_root"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return jsonify({"result": result.stdout.decode("utf-8")})


@app.route("/<path:path>")
def serve_static(path):
    return send_from_directory("static", path)


@app.route("/.well-known/ai-plugin.json", methods=["GET"])
def ai_plugin_info():
    return jsonify(
        {
            "schema_version": "v1",
            "name_for_human": "Mentat",
            "name_for_model": "mentat",
            "description_for_human": "Code with Mentat.",
            "description_for_model": api_system_prompt,
            "auth": {"type": "none"},
            "api": {"type": "openapi", "url": "http://localhost:3333/openapi.yaml"},
            "logo_url": "http://localhost:3333/logo.png",
            "contact_email": "support@example.com",
            "legal_info_url": "http://www.example.com/legal",
        }
    )
