from pathlib import Path
from textwrap import dedent
from typing import Any, AsyncGenerator, List

from mentat.llm_api_handler import chunk_to_lines
from mentat.parsers.file_edit import FileEdit, Replacement
from mentat.parsers.parser import ParsedLLMResponse
from mentat.session_context import SESSION_CONTEXT

"""
This parser is primarily intended as a utility for working with samples, rather than as a parser
for the LLM. We implement only those methods/properties which are necessary for that.

Things to be aware of:
1. git diffs include SHA-1 hashes, which link the diff to a known record in the git repo. When
    we generate diffs from scratch, we won't have these, so the diff can't be reverse-applied via
    `git apply myfile.diff`. The SHA-1 hashes should also be removed when comparing outputs in 
    tests as they are not expected to match.

2. git diffs include removed and to-be-modified lines, prefixed with a '-'. These are drawn from
    FileEdit.previous_file_lines field. When calling GitParser.file_edits_to_llm_message, 
    this field must be set (except for new files).

3. Each 'replacement' includes a 'hunk header' line, which is explained below for quick reference:

@@ -a,b +c,d @@

a = original starting line number
b = number of original lines changed, omitted if = 1
c = edited starting line number
d = number of edited lines in the change, ommitted if = 1
"""


class GitParser:
    # This doesn't actually "stream and parse" but it is named this way to match the interface of
    # the production parsers for use in the translation script.
    async def stream_and_parse_llm_response(
        self,
        response: AsyncGenerator[Any, None],
    ) -> ParsedLLMResponse:
        string = ""
        async for chunk in response:
            for content in chunk_to_lines(chunk):
                string += content
        return self.parse_llm_response(string)

    def parse_llm_response(self, content: str) -> ParsedLLMResponse:
        session_context = SESSION_CONTEXT.get()

        split_on_diff = content.split("diff --git")
        conversation = split_on_diff[0].strip()
        split_on_diff = split_on_diff[1:]
        git_diff = [f"diff --git{diff}" for diff in split_on_diff]

        # If there's a commit record, remove everything except the commit message.
        if "commit " in conversation and "\n\n" in conversation:
            conversation, commit_record = conversation.split("commit ", 1)
            commit_message = dedent(commit_record.split("\n\n")[1].strip())
            conversation += commit_message

        file_edits: List[FileEdit] = []
        for diff in split_on_diff:
            is_creation = "new file mode" in diff
            is_deletion = "deleted file mode" in diff
            first_line = diff.split("\n")[0]
            start_file_name = Path(first_line.split()[0][2:]).resolve()
            end_file_name = Path(first_line.split()[1][2:]).resolve()
            if start_file_name != end_file_name:
                new_name = end_file_name
            else:
                new_name = None

            file_edit = FileEdit(
                (session_context.cwd / start_file_name).resolve(),
                [],
                is_creation=is_creation,
                is_deletion=is_deletion,
                rename_file_path=new_name,
            )
            if not is_creation:
                file_edit.previous_file_lines = session_context.code_file_manager.file_lines.get(start_file_name, [])
            diff_split = diff.split("\n@@")
            if not is_deletion:
                for change in diff_split[1:]:
                    line_info = change.split("@@")[0]
                    # Git diff line represents line number information:
                    # @@ -a,b +c,d @@
                    # a is the original starting line number and b is the original number of lines.
                    # c and d are the new values.
                    # Both b and d are omitted when 1.
                    a_b = line_info.split()[0].split(",")
                    if is_creation:
                        start_line, end_line = 0, 0
                    else:
                        a = int(a_b[0][1:])
                        b = 1 if len(a_b) == 1 else int(a_b[1])
                        start_line = a - (1 if b > 0 else 0)
                        end_line = start_line + b
                    line_changes = change.split("@@")[1]
                    code_lines = line_changes.split("\n")[1:]  # Discard optional context
                    # This check is necessary because new code sometimes starts on the same line
                    # as @@ sometimes on the next line.
                    if code_lines[0] == "":
                        code_lines = code_lines[1:]
                    if code_lines[-1] == "":
                        code_lines = code_lines[:-1]

                    # Git diff gives context for human readability we don't want to train the llm
                    # to produce.
                    starting_repetition = 0
                    for line in code_lines:
                        if line.startswith(" "):
                            starting_repetition += 1
                        else:
                            break
                    ending_repetition = 0
                    for line in reversed(code_lines):
                        if line.startswith(" "):
                            ending_repetition += 1
                        else:
                            break
                    start_line += starting_repetition
                    end_line -= ending_repetition

                    lines: List[str] = []
                    for line in code_lines[starting_repetition : len(code_lines) - ending_repetition]:
                        if not line.startswith("-"):
                            lines.append(line[1:])

                    file_edit.replacements.append(Replacement(start_line, end_line, lines))

            file_edits.append(file_edit)

        return ParsedLLMResponse(f"{conversation}\n\n{git_diff}", conversation, file_edits)

    def file_edit_to_git_diff(self, file_edit: FileEdit) -> str:
        """Converts a FileEdit object into a git diff string."""
        session_context = SESSION_CONTEXT.get()
        cwd = session_context.cwd

        diff_lines: list[str] = []
        file_path_str = Path(file_edit.file_path).relative_to(session_context.cwd).as_posix()

        if file_edit.is_deletion:
            assert file_edit.previous_file_lines is not None, "Missing previous lines"
            diff_lines.append(f"diff --git a/{file_path_str} b/{file_path_str}")
            diff_lines.append("deleted file mode 100644")
            diff_lines.append("index fffffff..0000000")
            diff_lines.append(f"--- a/{file_path_str}")
            diff_lines.append("+++ /dev/null")
            diff_lines.append(f"@@ -1,{len(file_edit.previous_file_lines) - 1} +0,0 @@")
            for line in file_edit.previous_file_lines:
                diff_lines.append(f"-{line}")
            if diff_lines[-1] == "-":
                diff_lines = diff_lines[:-1]
            return "\n".join(diff_lines)

        if file_edit.is_creation:
            diff_lines.append(f"diff --git a/{file_path_str} b/{file_path_str}")
            diff_lines.append("new file mode 100644")
            diff_lines.append("index 0000000..fffffff")
            diff_lines.append("--- /dev/null")
            diff_lines.append(f"+++ b/{file_path_str}")
        elif file_edit.rename_file_path:
            new_file_path_str = file_edit.rename_file_path.relative_to(cwd).as_posix()
            diff_lines.append(f"diff --git a/{file_path_str} b/{new_file_path_str}")
            diff_lines.append("similarity index 100%")
            diff_lines.append(f"rename from {file_path_str}")
            diff_lines.append(f"rename to {new_file_path_str}")
        else:
            diff_lines.append(f"diff --git a/{file_path_str} b/{file_path_str}")
            diff_lines.append("index fffffff..fffffff 100644")
            diff_lines.append(f"--- a/{file_path_str}")
            diff_lines.append(f"+++ b/{file_path_str}")

        sorted_replacements = sorted(file_edit.replacements, key=lambda r: r.starting_line)
        net_change_in_lines: int = 0
        for replacement in sorted_replacements:
            if file_edit.is_creation:
                a = 0
                b = 0
            else:
                n_changed_lines = replacement.ending_line - replacement.starting_line
                a = replacement.starting_line + (1 if n_changed_lines > 0 else 0)
                b = n_changed_lines
            n_inserted_lines = len(replacement.new_lines)
            c = (
                replacement.starting_line
                + 1  # Git uses one-based indiexing
                - (1 if n_inserted_lines == 0 else 0)
                + net_change_in_lines
            )
            d = n_inserted_lines
            hunk_header = f"@@ -{a}" + (" " if b == 1 else f",{b} ") + f"+{c}" + (" @@" if d == 1 else f",{d} @@")
            net_change_in_lines += d - b
            diff_lines.append(hunk_header)

            if not file_edit.is_creation:
                assert file_edit.previous_file_lines is not None, "Missing previous lines"
                for line in range(a, a + b):
                    diff_lines.append(f"-{file_edit.previous_file_lines[line - 1]}")
            for line in replacement.new_lines:
                diff_lines.append(f"+{line}")

        return "\n".join(diff_lines)

    def file_edits_to_llm_message(self, parsedLLMResponse: ParsedLLMResponse) -> str:
        ans = parsedLLMResponse.conversation.strip() + "\n\n"
        for file_edit in parsedLLMResponse.file_edits:
            ans += self.file_edit_to_git_diff(file_edit) + "\n"

        return ans
