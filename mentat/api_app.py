import os
import subprocess
from typing import List, Set

import uvicorn
from fastapi import FastAPI
from fastapi.datastructures import State
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import Field, create_model

from .api_image_gen import (
    generate_code_change_image_and_lines,
    generate_path_tree_image,
)
from .code_change import CodeChange, CodeChangeAction
from .code_file_manager import CodeFileManager
from .config_manager import ConfigManager, image_cache_dir_path
from .git_handler import get_shared_git_root_for_paths
from .prompts import api_system_prompt

HOST = "localhost"
PORT = 3333

app = FastAPI()

image_cache_dir_path.mkdir(parents=True, exist_ok=True)

app.mount("/images", StaticFiles(directory=image_cache_dir_path))
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)


def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    openapi_schema = get_openapi(
        title="Mentat",
        version="0.1.0",
        description="Code with Mentat.",
        routes=app.routes,
    )
    # OpenAI not parsing nested components so we flatten them.
    openapi_schema["components"]["schemas"]["CodeChange"]["properties"]["action"] = (
        openapi_schema["components"]["schemas"]["CodeChangeAction"]
    )
    openapi_schema["components"]["schemas"]["StageChangesRequestBody"]["properties"][
        "changes"
    ]["items"] = openapi_schema["components"]["schemas"]["CodeChange"]
    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi


class AppState(State):
    paths: Set[str]
    exclude_paths: Set[str]
    available_paths: Set[str]
    focused_paths: Set[str]
    git_root: str
    config: ConfigManager
    code_file_manager: CodeFileManager
    staged_changes: dict

    def __init__(self, paths: Set[str], exclude_paths: Set[str]):
        super().__init__()
        self.paths = paths
        self.exclude_paths = exclude_paths
        self.focused_paths = set()
        self.git_root = get_shared_git_root_for_paths(self.paths)
        self.config = ConfigManager(self.git_root)
        self.available_paths = CodeFileManager(
            self.paths,
            self.exclude_paths,
            None,
            self.config,
            self.git_root,
        ).file_paths
        self.configure()

    def configure(self):
        self.code_file_manager = CodeFileManager(
            self.focused_paths,
            self.exclude_paths,
            None,
            self.config,
            self.git_root,
        )
        self.code_file_manager.get_code_message()


def run_api(paths: Set[str], exclude_paths: Set[str]):
    app.state = AppState(paths, exclude_paths)
    uvicorn.run(app, host=HOST, port=PORT)


@app.get("/get-all-paths", operation_id="getAllPaths", summary="Get all paths.")
def get_all_paths():
    return {
        "paths": sorted(list(app.state.available_paths)),
        "user_output_image": f"http://{HOST}:{PORT}/images/" + generate_path_tree_image(
            app.state.available_paths, app.state.git_root
        ),
    }


@app.post("/focus-on-paths", operation_id="focusOnPaths", summary="Focus on paths.")
def focus_on_paths(
    request_body: create_model("FocusOnPathsRequestBody", paths=(List[str], ...))
):
    request_paths: Set[str] = set(request_body.paths)
    invalid_paths = request_paths - app.state.available_paths

    if invalid_paths:
        return JSONResponse(
            status_code=400,
            content={
                "error": "Invalid paths provided. See getAllPaths for valid paths.",
                "invalid_paths": list(invalid_paths),
            },
        )

    app.state.focused_paths = request_paths
    app.state.staged_changes = None
    app.state.configure()

    return {"success": True}


@app.get(
    "/get-focused-paths", operation_id="getFocusedPaths", summary="Get focused paths."
)
def get_focused_paths():
    if not app.state.focused_paths:
        return JSONResponse(
            status_code=400,
            content={
                "error": (
                    "No focused paths. See getAllPaths for paths to set with"
                    " focusOnPaths."
                ),
            },
        )

    image_name = generate_path_tree_image(app.state.focused_paths, app.state.git_root)

    return {
        "paths": sorted(list(app.state.focused_paths)),
        "user_output_image": f"http://{HOST}:{PORT}/images/{image_name}",
    }


@app.get(
    "/get-repository-state",
    operation_id="getRepositoryState",
    summary="Get repository state.",
)
def get_repository_state():
    response = {"code_messages": app.state.code_file_manager.get_code_message()}

    if app.state.staged_changes:
        image_name, code_change_lines = generate_code_change_image_and_lines(
            app.state.staged_changes["code_changes"]
        )
        response["staged_changes"] = {
            "summary": app.state.staged_changes["summary"],
            "code_changes": code_change_lines,
            "user_output_image": f"http://{HOST}:{PORT}/images/{image_name}",
        }

    return response


@app.post(
    "/stage-changes",
    operation_id="stageChanges",
    summary="Stage changes.",
)
def stage_changes(
    request_body: create_model(
        "StageChangesRequestBody",
        summary=(str, ...),
        changes=(
            List[
                create_model(
                    "CodeChange",
                    action=(CodeChangeAction, ...),
                    file=(str, ...),
                    insertAfterLine=(int, Field(None, alias="insert-after-line")),
                    insertBeforeLine=(int, Field(None, alias="insert-before-line")),
                    startLine=(int, Field(None, alias="start-line")),
                    endLine=(int, Field(None, alias="end-line")),
                    codeLines=(List[str], Field(default=[])),
                )
            ],
            ...,
        ),
    )
):
    code_changes = []

    for code_change in request_body.changes:
        if (
            code_change.file not in app.state.focused_paths
            and code_change.action != CodeChangeAction.CreateFile
        ):
            return JSONResponse(
                status_code=400,
                content={
                    "error": "Invalid file provided. Must be in focused paths.",
                    "invalid_file": code_change.file,
                },
            )

        code_changes.append(
            CodeChange(
                code_change.dict(by_alias=True, exclude_none=True),
                code_change.codeLines,
                app.state.code_file_manager,
            )
        )

    app.state.staged_changes = {
        "summary": request_body.summary,
        "code_changes": code_changes,
    }

    image_name, code_change_lines = generate_code_change_image_and_lines(code_changes)

    return {
        "staged_changes": code_change_lines,
        "message": "Please confirm or clear the staged changes.",
        "user_output_image": f"http://{HOST}:{PORT}/images/{image_name}",
    }


@app.post(
    "/confirm-or-clear-staged-changes",
    operation_id="confirmOrClearStagedChanges",
    summary="Confirm or clear staged changes.",
)
def confirm_staged_changes(
    request_body: create_model(
        "ConfirmOrClearStagedChangesRequestBody",
        confirm=(bool, None),
        clear=(bool, None),
    )
):
    if not app.state.staged_changes:
        return JSONResponse(
            status_code=400,
            content={
                "error": "No staged changes. See stageChanges to stage changes.",
            },
        )

    if request_body.confirm:
        app.state.code_file_manager.write_changes_to_files(
            app.state.staged_changes["code_changes"]
        )
        app.state.staged_changes = None
        return {"message": "Changes applied."}
    elif request_body.clear:
        app.state.staged_changes = None
        return {"message": "Changes cleared."}
    else:
        return JSONResponse(
            status_code=400,
            content={
                "error": "Must provide confirm or clear.",
            },
        )


@app.get("/.well-known/ai-plugin.json", include_in_schema=False)
def ai_plugin_info():
    return {
        "schema_version": "v1",
        "name_for_human": "Mentat",
        "name_for_model": "mentat",
        "description_for_human": "Code with Mentat.",
        "description_for_model": api_system_prompt,
        "auth": {"type": "none"},
        "api": {"type": "openapi", "url": "http://localhost:3333/openapi.json"},
        "logo_url": "http://localhost:3333/logo.png",
        "contact_email": "support@example.com",
        "legal_info_url": "http://www.example.com/legal",
    }
