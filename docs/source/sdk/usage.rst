Python SDK Usage
================

The Python SDK allows you to use mentat in your python programs. If you have mentat installed you can use it like this:

.. code-block:: python

   from mentat import Mentat
   client = Mentat(paths=['README.md'])

   client.startup()
   client.call_mentat_auto_accept("Please fix the typos in the Readme.")
   client.shutdown()

All the same options are available as in the command line interface. You can use commands and change configuration by passing in a mentat.Config object.
