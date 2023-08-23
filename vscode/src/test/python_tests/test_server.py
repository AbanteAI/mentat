# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
"""
Test for linting over LSP.
"""
import time

from .lsp_test_client import constants, defaults, session, utils

TEST_FILE_PATH = constants.TEST_DATA / "sample1" / "sample.py"
TEST_FILE_URI = utils.as_uri(str(TEST_FILE_PATH))
SERVER_INFO = utils.get_server_info_defaults()
TIMEOUT = 10  # 10 seconds


def test_mentat_language_server():
    """Verify that the LanguageServer is working correctly."""

    actual = ''
    with session.LspSession() as ls_session:
        ls_session.initialize(defaults.VSCODE_DEFAULT_INITIALIZE)

        def _handler(params):
            nonlocal actual
            actual += params
        ls_session.set_notification_callback(session.MENTAT_SEND_CHUNK, _handler)

        data = ['test/path']
        ls_session._send_command(session.MENTAT_RESTART, data)

        # Server currently waits 0.5 seconds before sending a response
        time.sleep(0.6)
        expected = f'Mentat initialized with paths={data} exclude=None'
        assert actual == expected
