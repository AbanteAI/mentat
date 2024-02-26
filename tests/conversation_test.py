import pytest

from mentat.errors import ReturnToUser
from mentat.parsers.block_parser import BlockParser
from mentat.parsers.replacement_parser import ReplacementParser
from mentat.session_context import SESSION_CONTEXT


@pytest.mark.asyncio
async def test_midconveration_parser_change(mock_call_llm_api):
    session_context = SESSION_CONTEXT.get()
    config = session_context.config
    conversation = session_context.conversation

    config.parser = "block"
    messages = await conversation.get_messages()
    assert messages[0]["content"] == BlockParser().get_system_prompt()

    config.parser = "replacement"
    messages = await conversation.get_messages()
    assert messages[0]["content"] == ReplacementParser().get_system_prompt()


@pytest.mark.asyncio
async def test_no_parser_prompt(mock_call_llm_api):
    session_context = SESSION_CONTEXT.get()
    config = session_context.config
    conversation = session_context.conversation

    messages = await conversation.get_messages(include_code_message=True)
    assert len(messages) == 2
    messages = await conversation.get_messages()
    assert len(messages) == 1
    config.no_parser_prompt = True
    messages = await conversation.get_messages()
    assert len(messages) == 0


@pytest.mark.asyncio
async def test_add_user_message_with_and_without_image(mock_call_llm_api):
    session_context = SESSION_CONTEXT.get()
    conversation = session_context.conversation

    # Test with image
    test_message = "Hello, World!"
    test_image_url = "http://example.com/image.png"
    conversation.add_user_message(test_message, test_image_url)
    messages_with_image = await conversation.get_messages()
    assert len(messages_with_image) == 2  # System prompt + user message
    user_message_content_with_image = messages_with_image[-1]["content"]
    assert len(user_message_content_with_image) == 2  # Text + image
    assert user_message_content_with_image[0]["type"] == "text"
    assert user_message_content_with_image[0]["text"] == test_message
    assert user_message_content_with_image[1]["type"] == "image_url"
    assert user_message_content_with_image[1]["image_url"]["url"] == test_image_url

    # Test without image
    conversation.clear_messages()
    conversation.add_user_message(test_message)
    messages_without_image = await conversation.get_messages()
    assert len(messages_without_image) == 2  # System prompt + user message
    user_message_content_without_image = messages_without_image[-1]["content"]
    assert user_message_content_without_image == test_message


@pytest.mark.asyncio
async def test_raise_if_context_exceeded():
    session_context = SESSION_CONTEXT.get()
    config = session_context.config
    config.maximum_context = 0
    conversation = session_context.conversation
    with pytest.raises(ReturnToUser):
        await conversation.get_model_response()
