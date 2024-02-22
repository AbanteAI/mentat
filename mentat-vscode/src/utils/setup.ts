import { exec } from "child_process";
import { spawn } from "child_process";
import * as fs from "fs";
import * as net from "net";
import * as os from "os";
import * as path from "path";
import * as semver from "semver";
import * as util from "util";
import * as vscode from "vscode";

import { waitForPortToBeInUse } from "./tcp";

const aexec = util.promisify(exec);

async function installMentat(
    progress: vscode.Progress<{ message?: string; increment?: number }>
): Promise<string> {
    // Check mentat dir
    const mentatDir = path.join(os.homedir(), ".mentat");
    if (!fs.existsSync(mentatDir)) {
        fs.mkdirSync(mentatDir);
    }

    // Check python version
    progress.report({ message: "Mentat: Detecting Python version..." });
    const pythonCommands =
        process.platform === "win32"
            ? ["py -3.10", "py -3", "py"]
            : ["python3.10", "python3", "python"];
    let pythonCommand: string | null = null;
    for (const command of pythonCommands) {
        try {
            const { stdout } = await aexec(`${command} --version`);
            const versionMatch = stdout.match(/Python (\d+\.\d+)(?:\.\d+)?/);
            if (versionMatch) {
                const version = semver.coerce(versionMatch[1]);
                if (
                    semver.gte(
                        version || new semver.SemVer("3.10.0"),
                        new semver.SemVer("3.10.0")
                    )
                ) {
                    pythonCommand = command;
                    break;
                }
            }
        } catch (error) {
            continue;
        }
    }
    if (pythonCommand === null) {
        throw new Error(
            "Python 3.10 or above is not found on your system. Please install it and try again."
        );
    }

    // Check if venv exists
    const venvPath = path.join(mentatDir, ".venv");
    if (!fs.existsSync(venvPath)) {
        progress.report({ message: "Mentat: Creating Python environment..." });
        const createVenvCommand = `${pythonCommand} -m venv ${venvPath}`;
        await aexec(createVenvCommand);
    }
    const binFolder = path.join(
        venvPath,
        process.platform === "win32" ? "Scripts" : "bin"
    );
    const pythonLocation = path.join(binFolder, "python");

    // If mentat is already installed, this doesn't do much and is pretty fast
    progress.report({ message: "Mentat: Installing..." });
    const mentatVersion: string = vscode.workspace
        .getConfiguration("mentat")
        .get("mentatVersion")!;
    const versionString = mentatVersion ? `==${mentatVersion}` : "";
    await aexec(`${pythonLocation} -m pip install -U mentat${versionString}`);
    console.log("Installed Mentat");
    return binFolder;
}

async function startMentat(binFolder: string) {
    const mentatExecutable: string = path.join(binFolder, "mentat-server");
    const cwd = vscode.workspace.workspaceFolders?.at(0)?.uri?.path;
    if (cwd === undefined) {
        throw new Error("Unable to determine workspace directory.");
    }
    // TODO: Pass config options to mentat here
    // TODO: I don't think this will work on Windows (check to make sure)
    const server = spawn(mentatExecutable, [cwd]);

    server.stdout.on("data", (data: any) => {
        console.log(`Server Output: ${data}`);
    });
    server.stderr.on("data", (data: any) => {
        console.error(`Server Error: ${data}`);
    });
    server.on("close", (code: number) => {
        console.log(`Server exited with code ${code}`);
    });
    // TODO: pass the subprocess up to kill?
}

export async function setupServer(): Promise<net.Socket> {
    const serverHost: string = "127.0.0.1";
    const serverPort: number = 7798;

    const binFolder = await vscode.window.withProgress(
        { location: vscode.ProgressLocation.Notification },
        async (progress) => {
            return await installMentat(progress);
        }
    );
    await startMentat(binFolder);
    // TODO: What does this do??? Do we need it???
    await waitForPortToBeInUse({ port: serverPort, timeout: 5000 });

    const socket = net.connect({
        host: serverHost,
        port: serverPort,
    });
    return socket;
}
