import { ChildProcessWithoutNullStreams, exec } from "child_process";
import { spawn } from "child_process";
import * as fs from "fs";
import * as os from "os";
import * as path from "path";
import * as semver from "semver";
import * as util from "util";
import * as vscode from "vscode";
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
    const pythonCommands =
        process.platform === "win32"
            ? ["py -3.10", "py -3", "py"]
            : ["python3.10", "python3", "python"];
    let pythonCommand: string | undefined = undefined;
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
    if (pythonCommand === undefined) {
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

    // TODO: Auto update mentat if wrong version
    const { stdout } = await aexec(`${pythonLocation} -m pip show mentat`);
    const mentatVersion = stdout.split("\n").at(1)?.split("Version: ")?.at(1);
    if (mentatVersion === undefined) {
        progress.report({ message: "Mentat: Installing..." });
        await aexec(`${pythonLocation} -m pip install mentat`);
        console.log("Installed Mentat");
    }

    return binFolder;
}

async function startMentat(binFolder: string) {
    const mentatExecutable: string = path.join(binFolder, "mentat-server");
    const cwd =
        vscode.workspace.workspaceFolders?.at(0)?.uri?.path ?? os.homedir();

    // TODO: Pass config options to mentat here
    // TODO: I don't think this will work on Windows (check to make sure)
    const serverProcess = spawn(mentatExecutable, [cwd]);
    serverProcess.stdout.setEncoding("utf-8");
    serverProcess.stdout.on("data", (data: any) => {
        // console.log(`Server Output: ${data}`);
    });
    serverProcess.stderr.on("data", (data: any) => {
        console.error(`Server Error: ${data}`);
    });
    serverProcess.on("close", (code: number) => {
        console.log(`Server exited with code ${code}`);
    });
    return serverProcess;
}

export async function setupServer(): Promise<ChildProcessWithoutNullStreams> {
    const binFolder = await vscode.window.withProgress(
        { location: vscode.ProgressLocation.Notification },
        async (progress) => {
            return await installMentat(progress);
        }
    );
    const serverProcess = await startMentat(binFolder);
    return serverProcess;
}
