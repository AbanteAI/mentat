import * as net from "net";

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

export { isPortInUse, waitForPortToBeInUse };
