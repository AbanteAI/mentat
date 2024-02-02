.. _alternative_models:

🦙 Alternative Models
=====================

Azure
-----

To use the Azure API, provide the :code:`AZURE_OPENAI_ENDPOINT` (:code:`https://<your-instance-name>.openai.azure.com/`) and :code:`AZURE_OPENAI_KEY` environment variables instead of :code:`OPENAI_API_KEY`.

In addition, Mentat uses the :code:`gpt-4-1106-preview` model by default. When using Azure, you will have to set the model as described in :ref:`configuration` to the name you gave your Azure model.

.. warning::
    Due to changes in the OpenAI Python SDK, you can no longer use :code:`OPENAI_API_BASE` to access the Azure API with Mentat.

🦙 Local Models
---------------

In our experiments we have not found any non-openai models to be as good as even gpt-3.5-turbo with Mentat. That being said it is possible to use Mentat with other models with just a few steps. Mentat uses the OpenAI SDK to retrieve chat completions. This means that setting the `OPENAI_API_BASE` environment variable is enough to use any model that has the same response schema as OpenAI. To use models with different response schemas, we recommend setting up a litellm proxy as described `here <https://docs.litellm.ai/docs/proxy/quick_start>`__ and pointing `OPENAI_API_BASE` to the proxy. You can use local models run with ollama with the following steps:

First run ollama. Replace mixtral with whichever model you want to use.

.. code-block:: bash

    ollama pull mixtral
    ollama serve
    # Should see: listening on 127.0.0.1:11434

Next run the litellm proxy. In another terminal run:

.. code-block:: bash

    pip install 'litellm[proxy]'
    litellm --model ollama/mixtral --api_base http://localhost:11434 --drop_params
    # Should see: Uvicorn running on http://0.0.0.0:8000

Finally set the OPENAI_API_BASE in the terminal before running mentat.

.. code-block:: bash

    # In ~/.mentat/.env
    OPENAI_API_BASE=http://localhost:8000
    # or
    export OPENAI_API_BASE=http://localhost:8000
    mentat

.. note::

    When using a litellm proxy, the model set in Mentat's config will not affect the model being run. To change the model, rerun the litellm proxy with a different model. As mentat thinks it is talking to gpt-4-1106-preview you may want to set :code:`maximum_context`.

.. warning::

    Be sure to include the --drop_params argument when running the litellm proxy! Mentat uses some arguments (such as response_format) that may not be available in alternative models.

