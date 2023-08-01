from textwrap import dedent

from mentat.app import run

temp_file_name = "temp.py"
template_insert_content = "# I inserted this comment"
template_insert_expected_content = template_insert_content + "\n"
template_double_insert_expected_content = (
    template_insert_content + "\n\n" + template_insert_content
)
template_insert = dedent(f"""\
    @@start
    {{
        "file": "{temp_file_name}",
        "action": "insert",
        "insert-after-line": 0,
        "insert-before-line": 1
    }}
    @@code
    {template_insert_content}
    @@end
    """)
template_insert2 = dedent(f"""\
    @@start
    {{
        "file": "{temp_file_name}",
        "action": "insert",
        "insert-after-line": 1,
        "insert-before-line": 2
    }}
    @@code
    {template_insert_content}
    @@end
    """)


def error_test_template(
    mock_call_llm_api,
    mock_collect_user_input,
    mock_setup_api_key,
    changes,
):
    # Automatically set everything up given and use given changes
    with open(temp_file_name, "w") as f:
        f.write("")

    mock_collect_user_input.side_effect = [
        "Go!",
        "y",
        KeyboardInterrupt,
    ]
    mock_call_llm_api.set_generator_values([changes])

    run([temp_file_name])
    with open(temp_file_name, "r") as f:
        content = f.read()
    return content


# These tests should not accept any changes after the invalid one
def test_malformed_json(mock_call_llm_api, mock_collect_user_input, mock_setup_api_key):
    # Should stop and only allow applying changes up to that point, not including malformed change
    content = error_test_template(
        mock_call_llm_api,
        mock_collect_user_input,
        mock_setup_api_key,
        template_insert + dedent("""\
        @@start
        {{
            "malformed-json: [,
        }}
        @@code
        # My json is malformed :(
        @@end
        """) + template_insert2,
    )
    assert content == template_insert_expected_content


def test_unknown_action(mock_call_llm_api, mock_collect_user_input, mock_setup_api_key):
    # Should stop and only allow applying changes up to that point, not including unknown action change
    content = error_test_template(
        mock_call_llm_api,
        mock_collect_user_input,
        mock_setup_api_key,
        template_insert + dedent(f"""\
        @@start
        {{
            "file": "{temp_file_name}",
            "action": "unknown",
            "insert-after-line": 0,
            "insert-before-line": 1
        }}
        @@code
        # I am unknown
        @@end
        """) + template_insert2,
    )
    assert content == template_insert_expected_content


def test_indicator(mock_call_llm_api, mock_collect_user_input, mock_setup_api_key):
    # Test start indicator in change, code indicator outside change, code indicator inside code block,
    # code indicator for action without code, and end indicator while not creating change
    content = error_test_template(
        mock_call_llm_api,
        mock_collect_user_input,
        mock_setup_api_key,
        template_insert + dedent(f"""\
        @@start
        {{
            "file": "{temp_file_name}",
            "action": "insert",
            "insert-after-line": 0,
            "insert-before-line": 1
        }}
        @@code
        @@start
        # I am wrong
        @@end
        """) + template_insert2,
    )
    assert content == template_insert_expected_content

    content = error_test_template(
        mock_call_llm_api,
        mock_collect_user_input,
        mock_setup_api_key,
        template_insert + dedent(f"""\
        @@code
        @@start
        {{
            "file": "{temp_file_name}",
            "action": "insert",
            "insert-after-line": 0,
            "insert-before-line": 1
        }}
        @@code
        # I am wrong
        @@end
        """) + template_insert2,
    )
    assert content == template_insert_expected_content

    content = error_test_template(
        mock_call_llm_api,
        mock_collect_user_input,
        mock_setup_api_key,
        template_insert + dedent(f"""\
        @@start
        {{
            "file": "{temp_file_name}",
            "action": "insert",
            "insert-after-line": 0,
            "insert-before-line": 1
        }}
        @@code
        @@code
        # I am wrong
        @@end
        """) + template_insert2,
    )
    assert content == template_insert_expected_content

    content = error_test_template(
        mock_call_llm_api,
        mock_collect_user_input,
        mock_setup_api_key,
        template_insert + dedent(f"""\
        @@start
        {{
            "file": "{temp_file_name}",
            "action": "remove",
            "insert-after-line": 0,
            "insert-before-line": 1
        }}
        @@code
        # I am wrong
        @@end
        """) + template_insert2,
    )
    assert content == template_insert_expected_content

    content = error_test_template(
        mock_call_llm_api,
        mock_collect_user_input,
        mock_setup_api_key,
        template_insert + dedent("""\
        @@end
        """) + template_insert2,
    )
    assert content == template_insert_expected_content


# These tests should keep changes after the invalid change
def test_no_line_numbers(
    mock_call_llm_api, mock_collect_user_input, mock_setup_api_key
):
    # Should have line numbers
    content = error_test_template(
        mock_call_llm_api,
        mock_collect_user_input,
        mock_setup_api_key,
        template_insert + dedent(f"""\
        @@start
        {{
            "file": "{temp_file_name}",
            "action": "replace"
        }}
        @@code
        # I have no line numbers
        @@end
        """) + template_insert2,
    )
    assert content == template_double_insert_expected_content


def test_invalid_line_numbers(
    mock_call_llm_api, mock_collect_user_input, mock_setup_api_key
):
    # First line number should be <= the last line number
    content = error_test_template(
        mock_call_llm_api,
        mock_collect_user_input,
        mock_setup_api_key,
        template_insert + dedent(f"""\
        @@start
        {{
            "file": "{temp_file_name}",
            "action": "replace",
            "start-line": 10,
            "end-line": 4
        }}
        @@code
        # I have wrong line numbers
        @@end
        """) + template_insert2,
    )
    print(repr(content))
    assert content == template_double_insert_expected_content


def test_existing_file(mock_call_llm_api, mock_collect_user_input, mock_setup_api_key):
    # Creating file that already exists should fail
    content = error_test_template(
        mock_call_llm_api,
        mock_collect_user_input,
        mock_setup_api_key,
        template_insert + dedent(f"""\
        @@start
        {{
            "file": "{temp_file_name}",
            "action": "create-file"
        }}
        @@code
        # I already exist
        @@end
        """) + template_insert2,
    )
    print(repr(content))
    assert content == template_double_insert_expected_content


def test_file_not_in_context(
    mock_call_llm_api, mock_collect_user_input, mock_setup_api_key
):
    # Trying to access file not in context should fail
    content = error_test_template(
        mock_call_llm_api,
        mock_collect_user_input,
        mock_setup_api_key,
        template_insert + dedent("""\
        @@start
        {
            "file": "iamnotincontext",
            "action": "insert",
            "insert-after-line": 0,
            "insert-before-line": 1
        }
        @@code
        # I am not in context
        @@end
        """) + template_insert2,
    )
    print(repr(content))
    assert content == template_double_insert_expected_content
