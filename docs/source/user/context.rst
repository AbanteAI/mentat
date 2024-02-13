Context
=======

Context refers to portions of your code/files which are sent to the LLM along with your question/task. An LLM is only as good as its context. Therefore we provide a number of ways to manually manage and inspect context as well as a few tools to attempt to automatically select a context.

Files can be manually added to context as a command line argument when starting mentat or with the :code:`/include` command during a session. Files can be removed from context with the :code:`/exclude` command. Mentat always puts all included files into the system message sent to the LLM so you probably don't want to start mentat with :code:`mentat .`. If you do want mentat to intelligently select the context from your prompt you should run :code:`mentat -a` and mentat will build its own context. For more see :ref:`auto context`.

You can specify line ranges to add only a subset of a file to context by adding the starting line (inclusive) and ending line (exclusive) to the path. For example :code:`/include README.md:1-5,10-20` would add lines 1, 2, 3 and 4 and 10th to 19th lines to the LLMs context.

You can see the conversation exactly as the LLM sees it by running :code:`/viewer`. This command opens the transcript in a web browser. If you click a message from the LLM you will see the conversation as the LLM sees it. You can see past conversations by using the arrow keys.

.. _autocontext:

Auto Context
------------

If you enable auto context either by starting mentat with the :code:`-a` flag or by setting :code:`auto_context_tokens` to a positive number during a session then on every request mentat will put :code:`auto_context_tokens` (defaults to 5000 if :code:`-a` is used with no argument) many tokens to your system prompt code message. Those tokens are chosen via embeddings.

A similar thing one can do is use the :code:`/search` command to get related snippets of code and then add them to context from the search interface.

Manually included files are still included when you enable auto context so you shouldn't run :code:`mentat . -a`.

