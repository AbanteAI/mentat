import datetime
import json
from pathlib import Path

from mentat.code_feature import get_consolidated_feature_refs
from mentat.command.command import Command
from mentat.git_handler import get_diff_for_file, get_paths_with_git_diffs
from mentat.session_context import SESSION_CONTEXT


class ExampleCommand(Command, command_name="example"):
    async def apply(self, *args: str) -> None:
        from mentat.parsers.git_parser import GitParser
        from mentat.session_input import collect_user_input

        session_context = SESSION_CONTEXT.get()
        stream = session_context.stream
        code_context = session_context.code_context
        code_file_manager = session_context.code_file_manager
        conversation = session_context.conversation

        # Code Repo
        stream.send("Enter github url (default AbanteAI/mentat): ", color="light_blue")
        url = (
            await collect_user_input()
        ).data.strip() or "https://github.com/AbanteAI/mentat"

        # Commit (should be latest on MAIN to avoid squash merge issues)
        stream.send(
            "Enter starting diff target (default upstream/main): ", color="light_blue"
        )
        commit = (await collect_user_input()).data.strip() or "upstream/main"

        # Config: Items which are different from the default
        included_features = [
            f for fs in code_context.include_files.values() for f in fs
        ]
        include_files = get_consolidated_feature_refs(included_features)

        # Convo: Transcript of conversation (without system prompt + context)
        messages = [
            m for m in conversation.get_messages() if m["role"] in {"user", "assistant"}
        ]  # TODO Extract original prompt, or rewrite?

        # Accepted changes to the code
        errors = code_file_manager.history.undo()
        assert not errors, f"Errors while undoing: {errors}"
        code_edits = code_file_manager.history.undone_edits[-1].copy()

        # Context: Files/lines which were used to understand and make edits
        file_refs = {
            edit.file_path
            for edit in code_edits
            if (edit.is_deletion or edit.rename_file_path or len(edit.replacements) > 0)
        }

        # Diff of commit to pre-edited code
        changed_files = get_paths_with_git_diffs(commit)
        diff: list[str] = []
        for file in changed_files:
            git_diff = get_diff_for_file(commit, file)
            if git_diff:
                diff += git_diff.split("\n")
            else:
                # Generate diff-like output for new files
                diff += [
                    f"diff --git a/{file} b/{file}",
                    "new file mode 100644",
                    "--- /dev/null",
                    f"+++ b/{file}",
                    "@@ -0,0 +1 @@",
                ] + [f"+{line}" for line in file.read_text().split("\n")]
        if diff:
            diff_edits = GitParser().parse_string("\n".join(diff))
        else:
            diff_edits = []

        await code_file_manager.history.redo()

        example = {
            "repo": url,
            "commit": commit,
            "config": [str(f) for f in include_files],
            "convo": messages,
            "edits": [edit.to_json() for edit in code_edits],
            "context": [str(f) for f in file_refs],
            "diff": diff_edits,
        }

        fname = f"example_{datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.json"
        with open(fname, "w") as f:
            json.dump(example, f, indent=4)
        fpath = Path(fname).resolve()
        assert fpath

    @classmethod
    def argument_names(cls) -> list[str]:
        return []

    @classmethod
    def help_message(cls) -> str:
        return (
            "Generates a .json file containing complete record of current interaction"
        )
