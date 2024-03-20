from pathlib import Path
from textwrap import dedent

import pytest

from mentat.parsers.file_edit import FileEdit, Replacement
from mentat.revisor.revisor import revise_edit


@pytest.mark.asyncio
async def test_revision(mock_session_context, mock_call_llm_api):
    file_name = Path("file").resolve()
    mock_session_context.conversation.add_user_message("User Request")
    mock_session_context.code_file_manager.file_lines[file_name] = dedent(
        """\
        def hello_world():
            pass
        hello_world(
        """
    ).split("\n")

    mock_call_llm_api.set_unstreamed_values(
        dedent(
            """\
        --- 
        +++ 
        @@ -1,5 +1,5 @@
         def hello_world():
        -    pass
        +    print("Hello, World!")
        -hello_world(
        +hello_world()
        """
        )
    )

    replacement_text = dedent(
        """\
            print("Hello, World!
        hello_world()"""
    ).split("\n")
    file_edit = FileEdit(file_name, [Replacement(1, 4, replacement_text)], False, False)
    await revise_edit(file_edit)
    assert "\n".join(
        file_edit.get_updated_file_lines(mock_session_context.code_file_manager.file_lines[file_name])
    ) == dedent(
        """\
            def hello_world():
                print("Hello, World!")
            hello_world()"""
    )


@pytest.mark.asyncio
async def test_skip_deletion(mock_session_context, mock_call_llm_api):
    file_name = Path("file").resolve()
    mock_session_context.code_file_manager.file_lines[file_name] = []

    # This will error if not deletion
    file_edit = FileEdit(file_name, [Replacement(1, 4, [])], False, True)
    await revise_edit(file_edit)
    assert file_edit.replacements == [Replacement(1, 4, [])]
