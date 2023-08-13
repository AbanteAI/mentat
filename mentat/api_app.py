import subprocess
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

from .api_code_image_gen import generate_code_change_image
from .api_image_gen import generate_path_tree_image
from .prompts import api_system_prompt
from .code_change import CodeChange
from .code_file_manager import CodeFileManager
from .config_manager import ConfigManager, mentat_dir_path
from .git_handler import get_shared_git_root_for_paths


app = Flask(__name__, static_folder="static")
CORS(app)

paths = None
exclude_paths = None
git_root = None
config = None
code_file_manager = None
staged_changes = None
focused_paths = set()


def run_api(paths_, exclude):
    global paths, exclude_paths
    paths = paths_
    exclude_paths = exclude
    configure_app_state()
    app.run(debug=True, port=3333)


def configure_app_state():
    global paths, exclude_paths, git_root, config, code_file_manager, focused_paths
    git_root = get_shared_git_root_for_paths(focused_paths if focused_paths else paths)
    config = ConfigManager(git_root)
    code_file_manager = CodeFileManager(
        focused_paths if focused_paths else [],
        exclude_paths if exclude_paths is not None else [],
        None,
        config,
        git_root,
    )
    code_file_manager.get_code_message()


@app.route("/focus-paths", methods=["POST"])
def focus_paths():
    global focused_paths, staged_changes
    requested_paths = set(request.json.get("paths", []))
    all_paths = paths - exclude_paths if paths and exclude_paths else paths
    invalid_paths = requested_paths - all_paths
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

    focused_paths = requested_paths
    configure_app_state()
    staged_changes = None
    return jsonify({"focused": True})


@app.route("/get-focused-paths", methods=["GET"])
def get_focused_paths():
    response = {
        "paths": list(focused_paths) if focused_paths else [],
    }
    if focused_paths:
        response["user_output_image"] = generate_path_tree_image(
            focused_paths, git_root
        )
    return jsonify(response)


@app.route("/get-all-paths", methods=["GET"])
def get_all_paths():
    all_paths = set(paths)  # Start with a copy of the global paths
    if exclude_paths:
        all_paths -= set(exclude_paths)
    image_url = generate_path_tree_image(all_paths, git_root)
    return jsonify({"paths": sorted(list(all_paths)), "user_output_image": image_url})


@app.route("/get-repository-state", methods=["GET"])
def get_repo_state():
    if not focused_paths:
        return jsonify(
            {"message": "Please focus on a set of paths from all paths first."}
        )
    code_message = code_file_manager.get_code_message()
    response = {
        "code_message": code_message,
    }
    if staged_changes:
        response["staged_changes"] = {
            "summary": staged_changes.get("summary", ""),
            "code_changes": [
                code_change.to_dict()
                for code_change in staged_changes.get("code_changes", [])
            ],
        }
    return jsonify(response)


@app.route("/confirm-staged-change", methods=["POST"])
def confirm_staged_change():
    global staged_changes, code_file_manager
    accept = request.json.get("accept")
    clear = request.json.get("clear")
    response = {"no-change": True}
    if accept:
        if staged_changes:
            code_file_manager.write_changes_to_files(
                staged_changes.get("code_changes", [])
            )
            staged_changes = None
            response = {"applied": True}
    elif clear:
        staged_changes = None
        response = {"cleared": True}
    return jsonify(response)


@app.route("/suggest-change", methods=["POST"])
def suggest_change():
    global staged_changes, git_root, code_file_manager
    summary = request.json.get("summary")
    code_changes = [
        CodeChange(
            code_change, code_change.get("code_lines", []), git_root, code_file_manager
        )
        for code_change in request.json.get("code_changes")
    ]
    image_url = generate_code_change_image(code_changes)
    staged_changes = {"summary": summary, "code_changes": code_changes}
    response = {
        "staged_changes": {
            "summary": summary,
            "code_changes": [code_change.to_dict() for code_change in code_changes],
        },
        "message": "Please confirm or clear the staged changes.",
        "user_output_image": image_url,
    }
    return jsonify(response)


@app.route("/execute-subprocess-command", methods=["POST"])
def execute_subprocess_command():
    if not config.api_allow_subprocess_commands():
        return (
            jsonify(
                {"error": "Subprocess commands are not allowed. Must enable in config."}
            ),
            403,
        )
    command = request.json.get("command")
    result = subprocess.run(
        command.split(), cwd=git_root, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    return jsonify({"result": result.stdout.decode("utf-8")})


@app.route("/<path:path>")
def serve_static(path):
    return send_from_directory("static", path)


@app.route("/.well-known/ai-plugin.json", methods=["GET"])
def ai_plugin_info():
    plugin_info = {
        "schema_version": "v1",
        "name_for_human": "Mentat Plugin",
        "name_for_model": "mentat_plugin",
        "description_for_human": "Code with Mentat.",
        "description_for_model": api_system_prompt,
        "auth": {"type": "none"},
        "api": {"type": "openapi", "url": "http://localhost:3333/openapi.yaml"},
        "logo_url": "http://localhost:3333/logo.png",
        "contact_email": "support@example.com",
        "legal_info_url": "http://www.example.com/legal",
    }
    return jsonify(plugin_info)
