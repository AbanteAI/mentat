import { exec } from "child_process"
import { spawn } from "child_process"
import * as fs from "fs"
import * as net from "net"
import * as os from "os"
import * as path from "path"
import * as semver from "semver"
import * as util from "util"
import * as vscode from "vscode"
import { ServerOptions, StreamInfo } from "vscode-languageclient/node"

import { getGitRoot } from "./git"
import { waitForPortToBeInUse } from "./tcp"

// const PIP_INSTALL_ARGS = `install --upgrade "git+https://github.com/AbanteAI/mentat.git@main"`;
const PIP_INSTALL_ARGS = `install "/Users/waydegg/ghq/github.com/AbanteAI/mentat"`

const aexec = util.promisify(exec)

async function installMentat(
  progress: vscode.Progress<{ message?: string; increment?: number }>
) {
  console.log("Executing: const mentatDir = path.join(os.homedir(), '.mentat');")
  const mentatDir = path.join(os.homedir(), ".mentat")
  console.log("Executing: if (!fs.existsSync(mentatDir))...")
  if (!fs.existsSync(mentatDir)) {
    console.log("Executing: fs.mkdirSync(mentatDir);")
    fs.mkdirSync(mentatDir)
  }
  progress.report({ message: "Mentat: Detecting Python version..." })
  const pythonCommands =
    process.platform === "win32"
      ? ["py -3.10", "py -3", "py"]
      : ["python3.10", "python3", "python"]
  console.log("Executing: let pythonCommand: string | null = null;")
  let pythonCommand: string | null = null
  console.log("Executing: for... loop over pythonCommands")
  for (const command of pythonCommands) {
    console.log(`Command: ${command}`)
    try {
      const { stdout } = await aexec(`${command} --version`)
      const versionMatch = stdout.match(/Python (\d+\.\d+)(?:\.\d+)?/)
      if (versionMatch) {
        // Coerce the matched version to a semver object
        const version = semver.coerce(versionMatch[1])
        // Compare the coerced version with the desired version
        if (
          semver.gte(
            version || new semver.SemVer("3.10.0"),
            new semver.SemVer("3.10.0")
          )
        ) {
          pythonCommand = command
          break
        }
      }
    } catch (error) {
      continue
    }
  }

  if (pythonCommand === null) {
    throw new Error(
      "Python 3.10 or above is not found on your system. Please install it and try again."
    )
  }
  progress.report({ message: "Mentat: Creating Python environment..." })
  const createVenvCommand = `${pythonCommand} -m venv ${mentatDir}/venv`
  console.log(`Executing: ${createVenvCommand}`)
  await aexec(createVenvCommand)

  progress.report({ message: "Mentat: Building Server..." })
  const venvPath =
    process.platform === "win32"
      ? `${mentatDir}\\venv\\Scripts\\`
      : `${mentatDir}/venv/bin/`

  const activateVenvAndInstallMentatCommand = venvPath + `pip ${PIP_INSTALL_ARGS}`
  console.log(`Executing: ${activateVenvAndInstallMentatCommand}`)
  await aexec(activateVenvAndInstallMentatCommand)
  await vscode.workspace
    .getConfiguration("mentat")
    .update("mentatPath", venvPath + "mentat-server", true)

  console.log("Installed Mentat")
}

async function createMentatProcess(port: number) {
  const mentatPath: string = await vscode.workspace
    .getConfiguration("mentat")
    .get("mentatPath")!

  const ls = spawn(mentatPath)

  ls.stdout.on("data", (data: any) => {
    console.log(`stdout: ${data}`)
  })

  ls.stderr.on("data", (data: any) => {
    console.error(`stderr: ${data}`)
  })

  ls.on("close", (code: number) => {
    console.log(`child process exited with code ${code}`)
  })
}

async function createMentatSocket(args: {
  host: string
  port: number
}): Promise<ServerOptions> {
  // await waitForPortToBeInUse({ port: args.port, timeout: 5000 })

  const socket = net.connect({
    host: args.host,
    port: args.port,
  })
  const streamInfo: StreamInfo = {
    reader: socket,
    writer: socket,
  }

  return () => {
    return Promise.resolve(streamInfo)
  }
}

async function getLanguageServerOptions(): Promise<ServerOptions> {
  const workspaceConfig = vscode.workspace.getConfiguration("mentat")
  const languageServerHost: string = workspaceConfig.get("languageServerHost")!
  const languageServerPort: number = workspaceConfig.get("languageServerPort")!

  // await spawnMentatProcess(port);

  console.log("Getting Mentat Socket")
  const serverOptions = await createMentatSocket({
    host: languageServerHost,
    port: languageServerPort,
  })
  console.log("Got Mentat Socket")

  return serverOptions
}

export { installMentat, getLanguageServerOptions }
