import * as net from "net";
import { ServerOptions, StreamInfo } from "vscode-languageclient/node";

async function isPortInUse(port: number): Promise<boolean> {
  return new Promise((resolve) => {
    const tester: net.Socket = net.createConnection(port);

    tester.once("connect", () => {
      resolve(true);
      tester.end();
    });

    tester.on("error", (err: Error & { code?: string }) => {
      if (err.code === "ECONNREFUSED") {
        resolve(false);
      } else {
        console.error("Unexpected error:", err);
        resolve(false); // Consider how you want to handle unexpected errors
      }
    });
  });
}

async function waitForPortToBeInUse(port: number, timeout: number): Promise<void> {
  const startTime = Date.now();

  while (true) {
    if (await isPortInUse(port)) {
      console.log(`Port ${port} is now in use`);
      return;
    }

    // Check for timeout
    if (Date.now() - startTime > timeout) {
      throw new Error(`Timeout waiting for port ${port} to be in use`);
    }

    // Wait for a short period before checking again
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
}

/** Creates the ServerOptions for a system in the case that a language server is already running on the given port. */
function tcpServerOptions(port: number): ServerOptions {
  const socket = net.connect({
    port: port,
    host: "127.0.0.1",
  });
  const streamInfo: StreamInfo = {
    reader: socket,
    writer: socket,
  };
  return () => {
    return Promise.resolve(streamInfo);
  };
}

export { isPortInUse, waitForPortToBeInUse, tcpServerOptions };
