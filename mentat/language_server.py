from typing import Any

from pygls.server import LanguageServer

server = LanguageServer(name="mentat-server", version="v0.1")


@server.feature("mentat/chatMessage")
async def get_chat_message(params: Any):
    print("Got: ", params)


print("starting tpc server")
server.start_tcp("127.0.0.1", 8080)
