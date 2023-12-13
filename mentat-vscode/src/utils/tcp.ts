import * as net from "net"

async function isPortInUse(port: number): Promise<boolean> {
  return new Promise((resolve) => {
    const tester: net.Socket = net.createConnection(port)

    tester.once("connect", () => {
      resolve(true)
      tester.end()
    })

    tester.on("error", (err: Error & { code?: string }) => {
      if (err.code === "ECONNREFUSED") {
        resolve(false)
      } else {
        console.error("Unexpected error:", err)
        resolve(false) // Consider how you want to handle unexpected errors
      }
    })
  })
}

async function waitForPortToBeInUse(args: {
  port: number
  timeout: number
}): Promise<void> {
  const startTime = Date.now()

  while (true) {
    if (await isPortInUse(args.port)) {
      console.log(`Port ${args.port} is now in use`)
      return
    }

    // Check for timeout
    if (Date.now() - startTime > args.timeout) {
      throw new Error(`Timeout waiting for port ${args.port} to be in use`)
    }

    // Wait for a short period before checking again
    await new Promise((resolve) => setTimeout(resolve, 500))
  }
}

export { isPortInUse, waitForPortToBeInUse }
