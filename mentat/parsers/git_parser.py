from pathlib import Path
from textwrap import dedent
from typing import Any, AsyncGenerator, List

from mentat.llm_api_handler import chunk_to_lines
from mentat.parsers.file_edit import FileEdit, Replacement
from mentat.parsers.parser import ParsedLLMResponse
from mentat.session_context import SESSION_CONTEXT

# The git diff format should not be used with an LLM because it contains information like SHAs
# which it would not know about. It also involves certain arithmetic that it couldn't reliably do
# and typically prints out extra lines which aid human readability but would cost tokens.
# It is implemented to create training data from git diffs. Therefore there's not need for it to
# work asynchronously or stream partial results. In theory one could work this into the existing
# Parser class but it is simpler to assume one has the whole string up front and make heavy use of
# split.


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
        return self.parse_string(string)

    def parse_string(self, git_diff: str) -> ParsedLLMResponse:
        session_context = SESSION_CONTEXT.get()
        git_root = session_context.git_root

        # This is safe because actual code is prepended with ' ', + or -.
        split_on_diff = git_diff.split("\ndiff --git ")

        # Use commit message for conversation
        commit_message = dedent(split_on_diff[0].split("\n\n")[1].strip())

        file_edits: List[FileEdit] = []
        for diff in split_on_diff[1:]:
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
                git_root / start_file_name,
                [],
                is_creation=is_creation,
                is_deletion=is_deletion,
                rename_file_path=new_name,
            )
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
                    start_line = int(a_b[0][1:]) - 1
                    if len(a_b) == 1:
                        end_line = start_line + 1
                    else:
                        end_line = start_line + int(a_b[1])
                    line_changes = change.split("@@")[1]
                    code_lines = line_changes.split("\n")
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
                    for line in code_lines[
                        starting_repetition : len(code_lines) - ending_repetition
                    ]:
                        if not line.startswith("-"):
                            lines.append(line[1:])

                    file_edit.replacements.append(
                        Replacement(start_line, end_line, lines)
                    )

            file_edits.append(file_edit)

        return ParsedLLMResponse(git_diff, commit_message, file_edits)
