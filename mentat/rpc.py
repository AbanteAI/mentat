class RpcServer:
    """A JSON RPC server that sends and receives data.

    See https://github.com/morph-labs/rift/blob/350a4195077ec2d1ec9b415a19afb6d84c8c69f7/rift-engine/rift/rpc/jsonrpc.py
    """

    async def serve(self):
        """Open a TCP connection with a client.

        This is an infinitely running loop that:
        - routes requests from the client to RPC methods `MentatEngine` exposes
        - sends responses to the client
        """

    async def _on_startup(self):
        ...

    async def _on_shutdown(self):
        ...

    async def _send(self, wait_for_response: bool = False):
        """Send a request to the client"""

    async def _recv(self):
        """Receive a request from the client and route to RPC methods"""
