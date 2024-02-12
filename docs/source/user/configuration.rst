Configuration
=============

Mentat has a number of customizable settings. They can be changed globally by setting in :code:`~/.mentat/.mentat_config.json` or on a per project level by setting in :code:`.mentat_config.json`. They can also be set as a command line flag, see :ref:`cli_args`, note underscores become dashes on the cli. Finally they can be changed mid-session with the :code:`/config` command.

The following is a partial list of customizable settings.

Settings
--------
model
^^^^^

The model used for making edits. We recommend sticking to gpt-4-1106-preview. For changing to non-openai models see :ref:`alternative_models`.

maximum_context
^^^^^^^^^^^^^^^

The maximum number of tokens to put into context. When using an openai model this defaults to the model's maximum context. Otherwise it defaults to 4096.

auto_context_tokens
^^^^^^^^^^^^^^^^^^^

When this is set to a positive integer that many tokens of additional context are selected with an embeddings system and put into context. For more see :ref:`autocontext`.

theme
^^^^^

Currently only :code:`dark` and :code:`light` are supported.

temperature
^^^^^^^^^^^

The temperature used by the edit generating model. This defaults to 0.2.

no_parser_prompt
^^^^^^^^^^^^^^^^

When this is set to true the model isn't given a system prompt describing how to make edits. This should only be set for fine tuned models.

embedding_model
^^^^^^^^^^^^^^^

The model used for making embeddings.

file_exclude_glob_list
^^^^^^^^^^^^^^^^^^^^^^

List of `glob patterns <https://docs.python.org/3/library/glob.html>`_ to exclude files from being read/edited by Mentat. These take effect whenever you provide Mentat with a directory as an argument. Mentat will add all files in the directory that are not in your :code:`.gitignore` and do not match these glob patterns. Glob patterns are interpreted from the git root location. If you wanted to exclude all files ending in :code:`.py`, the pattern to use would be :code:`**/*.py` rather than :code:`*.py`. Here is an example that would exclude all hidden directories and files:

.. code-block:: json

    {
        "file-exclude-glob-list": ["**/.*, **/.*/**"]
    }

parser
^^^^^^

Mentat is able to edit files by parsing a specific format that the model is told to follow. We are always working to improve the format we use, and have multiple formats available. Although we expect the default format to perform the best, you can test out other formats using the configuration.

.. code-block:: json

    {
        "parser": "block"
    }

Available formats:

- `block <https://github.com/AbanteAI/mentat/blob/main/mentat/parsers/block_parser.py>`_
- `replacement <https://github.com/AbanteAI/mentat/blob/main/mentat/parsers/replacement_parser.py>`_
- `unified-diff <https://github.com/AbanteAI/mentat/blob/main/mentat/parsers/unified_diff_parser.py>`_
