from mentat.parsers.block_parser import BlockParser
from mentat.parsers.replacement_parser import ReplacementParser
from mentat.session_context import SESSION_CONTEXT


def test_midconveration_parser_change(mock_session_context):
    session_context = SESSION_CONTEXT.get()
    config = session_context.config
    conversation = session_context.conversation

    config.parser = "block"
    assert conversation.get_messages()[0].text == BlockParser().get_system_prompt()

    config.parser = "replacement"
    assert (
        conversation.get_messages()[0].text == ReplacementParser().get_system_prompt()
    )


def test_no_parser_prompt(mock_session_context):
    session_context = SESSION_CONTEXT.get()
    config = session_context.config
    conversation = session_context.conversation

    assert len(conversation.get_messages()) == 1
    config.no_parser_prompt = True
    assert len(conversation.get_messages()) == 0
