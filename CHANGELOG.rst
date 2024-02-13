Changelog
=========

In this changelog focus on user facing highlights and stick to the format. This information will be used to motivate users to upgrade or after upgrading to inform them of features that might otherwise not be very discoverable.

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
