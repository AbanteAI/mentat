Changelog
=========

In this changelog focus on user facing highlights and stick to the format. This information will be used to motivate users to upgrade or after upgrading to inform them of features that might otherwise not be very discoverable.

`1.0.18 <https://pypi.org/project/mentat/1.0.18/>`__
--------------------------------------------------

- Bug fixes and dependency updates

`1.0.17 <https://pypi.org/project/mentat/1.0.17/>`__
--------------------------------------------------

- Fix requirement conflict for numpy

`1.0.16 <https://pypi.org/project/mentat/1.0.16/>`__
--------------------------------------------------

- Always use the latest patch-level versions of Spice and Ragdaemon

`1.0.15 <https://pypi.org/project/mentat/1.0.15/>`__
--------------------------------------------------

- Improved auto-context selection and generation
- Improved token counting, cost tracking, and message conversion for Anthropic models
- Fixed vision inputs with Anthropic models
- Switched default model to gpt-4-turbo

`1.0.14 <https://pypi.org/project/mentat/1.0.14/>`__
--------------------------------------------------

- Fixed bugs relating to VSCode extension
- Updated dependencies

`1.0.13 <https://pypi.org/project/mentat/1.0.13/>`__
--------------------------------------------------

- Claude 3 support
- All Anthropic models can now be used without requiring a LiteLLM proxy

`1.0.12 <https://pypi.org/project/mentat/1.0.12/>`__
--------------------------------------------------

- Added helpful message when no api key found
- Fixed errors relating to embedding models

`1.0.11 <https://pypi.org/project/mentat/1.0.11/>`__
--------------------------------------------------

- Added /save and /load command to save and load context selections
- Changed format to fit Anthropic models
- Other bug fixes

`1.0.10 <https://pypi.org/project/mentat/1.0.10/>`__
--------------------------------------------------

- Mentat is now a full terminal app which displays the context and running cost in the sidebar.
- Mentat now has a python sdk. Try `from mentat import Mentat` to get started. See the docs for more details.
- New openai models added to the model list.

`1.0.9 <https://pypi.org/project/mentat/1.0.9/>`__
--------------------------------------------------

- Adds `/amend` command: clear last message and prefill with last prompt.
- Experimental feature revisor. Turn on with `--revisor` flag. Attempts to fix edits that fail to conform to parser format.
- Switch to ChromaDB for embeddings.

`1.0.8 <https://pypi.org/project/mentat/1.0.8/>`__
--------------------------------------------------

- Auto context now only grows so the model won't forget earlier read files.
- Faster embeddings for search and auto context.
- Share button added to `/viewer`.
- Improved documentation for non OpenAI models.

`1.0.7 <https://pypi.org/project/mentat/1.0.7/>`__
--------------------------------------------------

- `/search` command now has UI to add found files to context.
- Feedback button added to `/viewer`.
- Command and file autocompletion.
