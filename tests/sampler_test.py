import pytest
from openai.types.chat import (
    ChatCompletionAssistantMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
)

from mentat.sampler.sample import Sample

@pytest.mark.asyncio
async def test_sample_from_context(
    mocker, 
    temp_testbed, 
    mock_session_context, 
    mock_collect_user_input,
):
    
    mock_session_context.config.sample_merge_base_target = "test_smbt"
    mock_session_context.config.sample_repo = "test_sample_repo"

    edit_history = mock_session_context.code_file_manager.history
    edit_history.merge_base = "test_merge_base"
    edit_history.diff_merge_base = "test_diff_merge_base"
    edit_history.diff_active = "test_diff_active"
    edit_history.hexsha_active = "test_hexsha_active"
    
    mocker.patch(
        "mentat.conversation.Conversation.get_messages", 
        return_value=[
            ChatCompletionSystemMessageParam(
                content="test_system_content",
                role="system",
            ),
            ChatCompletionUserMessageParam(
                content="test_user_content",
                role="user",
            ),
            ChatCompletionAssistantMessageParam(
                content="test_assistant_content",
                role="assistant",
            ),
        ]
    )

    mock_session_context.code_context.include(
        "multifile_calculator/operations.py",
    )

    with open("test_file.py", "w") as f:
        f.write("test_file_content")

    mock_collect_user_input.set_stream_messages(
        [
            "test_title",
            "test_description",
            "test_test_command",
        ]
    )

    sample = await Sample.from_context()
    assert sample.title == "test_title"
    assert sample.description == "test_description"
    assert sample.repo == "test_sample_repo"
    assert sample.merge_base == "test_merge_base"
    assert sample.diff_merge_base == "test_diff_merge_base"
    assert sample.diff_active == "test_diff_active"
    assert sample.hexsha_active == "test_hexsha_active"
    assert sample.messages == [
        {"role": "user", "content": "test_user_content"},
        {"role": "assistant", "content": "test_assistant_content"}
    ]
    assert sample.args == ["multifile_calculator/operations.py"]
    assert sample.diff_edit == "diff --git a/test_file.py b/test_file.py\nnew file mode 100644\nindex 0000000..ffffff\n--- /dev/null\n+++ b/test_file.py\n@@ -0,0 +1 @@\n+test_file_content"
    assert sample.hexsha_edit != ""
    assert sample.test_command == "test_test_command"
    assert sample.version == "0.1.0"
