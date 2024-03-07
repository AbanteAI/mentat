Commands
========

In addition to the standard chat interface there are a number of commands available to do things such as modify or observe the context, run shell commands, use vision and voice, and more. You can get help information for them in a session by running the :code:`/help` command.

/agent
------

Toggle agent mode. In agent mode Mentat will automatically make changes and run commands.

/clear
------

Clear the current message history and auto included code features from context.

/commit [commit message]
------------------------

Commit all unstaged and staged changes to git.

/config <setting> [value]
-------------------------

Show or set a config option's value.

/exclude <path|glob pattern> ...
--------------------------------

Remove files from context.

/help [command] ...
-------------------

Show information on available commands.

/include <path|glob pattern> ...
--------------------------------

Add files to context.

/load [context file path]
------------

Load context from a file.

/save [context file path]
------------

Save context to a file.

/redo
-----

Redo a change that was previously undone with /undo.

/run <command> [args] ...
-------------------------

Run a shell command and put its output in context. For example, run a python script with arguments:

:code:`\run python my_script.py arg1 arg2`

This command is very useful to avoid copy pasting. Instead of pasting the test output into mentat and asking mentat to fix it, simply run the test in mentat.

/screenshot [path|url]
----------------------

Open a url or local file in a web browser with Selenium, take a screenshot and put it into the model's context. The model is automatically changed to gpt-4-vision-preview if an openai model that doesn't support vision is currently set.

/search <query>
---------------

Search files in context semantically with embeddings. Results can be added to context directly from the search interface.

/talk
-----

Start voice to text. Uses whisper via the openai api.

/undo
-----

Undo the last change made by Mentat.

/undo-all
---------

Undo all changes made by Mentat.

/viewer
-------

Open a webpage showing the conversation so far. Model messages can be clicked to show the conversation from the model's perspective. There are buttons to share the conversation or give feedback.

/amend
-------

Used to amend a previous user request. Works by resetting context to the state it was at the last request and prefills user input with the last request. Does not undo any edits.
