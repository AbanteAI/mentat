import { ChildProcess, exec } from "child_process";
import { spawn } from "child_process";
import EventEmitter from "events";
import * as fs from "fs";
import * as os from "os";
import * as path from "path";
import * as semver from "semver";
import { Writable } from "stream";
import { StreamMessage } from "types";
import * as util from "util";
import { v4 } from "uuid";
import * as vscode from "vscode";

// IMPORTANT: This MUST be updated with the vscode extension to ensure that the right mentat version is installed!
const MENTAT_VERSION = "1.0.14";

const aexec = util.promisify(exec);

class Server {
    private binFolder: string | undefined = undefined;
    private serverProcess: ChildProcess | undefined;
    public messageEmitter: EventEmitter = new EventEmitter();
    private backlog: StreamMessage[] = [];

    constructor() {}

    private async installMentat(
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
                const versionMatch = stdout.match(
                    /Python (\d+\.\d+)(?:\.\d+)?/
                );
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
            progress.report({
                message: "Mentat: Creating Python environment...",
            });
            const createVenvCommand = `${pythonCommand} -m venv ${venvPath}`;
            try {
                await aexec(createVenvCommand);
            } catch (error) {
                throw new Error(`Error creating Python venv: ${error}`);
            }
        }
        const binFolder = path.join(
            venvPath,
            process.platform === "win32" ? "Scripts" : "bin"
        );
        const pythonLocation = path.join(binFolder, "python");

        var mentatVersion;
        try {
            const { stdout } = await aexec(
                `${pythonLocation} -m pip show mentat`
            );
            mentatVersion = stdout
                .split("\n")
                .at(1)
                ?.split("Version: ")
                ?.at(1)
                ?.trim();
        } catch (error) {
            mentatVersion = null;
        }
        if (mentatVersion !== MENTAT_VERSION) {
            progress.report({ message: "Mentat: Installing..." });
            try {
                await aexec(
                    `${pythonLocation} -m pip install mentat==${MENTAT_VERSION}`,
                    { env: { ...process.env, HNSWLIB_NO_NATIVE: "1" } }
                );
            } catch (error) {
                throw new Error(`Error installing Mentat: ${error}`);
            }
            console.log("Installed Mentat");
        }

        return binFolder;
    }

    private collectConfigOptions(): string[] {
        const configuration = vscode.workspace.getConfiguration("mentat");
        const optionNames = [
            "model",
            "embedding-model",
            "temperature",
            "maximum-context",
            "token-buffer",
            "auto-context-tokens",
        ];
        const configOptions: string[] = [];
        for (const optionName of optionNames) {
            const configValue = configuration.get(optionName);
            if (configValue !== undefined && configValue !== null) {
                configOptions.push(`--${optionName}=${configValue.toString()}`);
            }
        }

        return configOptions;
    }

    private async startMentat(workspaceRoot: string, binFolder: string) {
        const mentatExecutable: string = path.join(binFolder, "mentat-server");

        const serverProcess = spawn(
            mentatExecutable,
            [workspaceRoot, ...this.collectConfigOptions()],
            { stdio: [null, null, null, "pipe", "pipe"] }
        );
        if (serverProcess.stdout) {
            serverProcess.stdout.on("data", (data: any) => {
                console.log(`Server Output: ${data}`);
            });
        }
        if (serverProcess.stderr) {
            serverProcess.stderr.on("data", (data: any) => {
                console.error(`Server Error: ${data}`);
            });
        }
        serverProcess.on("close", (code: number) => {
            console.log(`Server exited with code ${code}`);
        });
        return serverProcess;
    }

    private curMessage: string = "";

    public async startServer(workspaceRoot: string) {
        if (this.binFolder === undefined) {
            this.binFolder = await vscode.window.withProgress(
                { location: vscode.ProgressLocation.Notification },
                async (progress) => {
                    return await this.installMentat(progress);
                }
            );
        }
        if (this.serverProcess !== undefined) {
            this.backlog = [];
            this.serverProcess.kill();
        }
        this.serverProcess = await this.startMentat(
            workspaceRoot,
            this.binFolder
        );
        this.serverProcess.stdio[4]?.on("data", (rawOutput: Buffer) => {
            const output = rawOutput.toString("utf-8");
            this.curMessage += output;
            if (!this.curMessage.endsWith("\n")) {
                return;
            }
            for (const serializedMessage of this.curMessage
                .trim()
                .split("\n")) {
                try {
                    const message: StreamMessage = JSON.parse(
                        serializedMessage.trim()
                    );
                    this.messageEmitter.emit("message", message);
                } catch (error) {
                    console.error("Error reading StreamMessage:", error);
                }
            }
            this.curMessage = "";
        });
        this.clearBacklog();
    }

    public closeServer() {
        if (this.serverProcess !== undefined) {
            this.serverProcess.kill();
        }
    }

    /**
     * Convenience method for sending data over a specific channel
     */
    public sendStreamMessage(
        data: any,
        channel: string,
        extra: { [key: string]: any } = {}
    ) {
        const message: StreamMessage = {
            id: v4(),
            channel: channel,
            source: "client",
            data: data,
            extra: extra,
        };
        this.sendMessage(message);
    }

    private writeMessage(message: StreamMessage) {
        // @ts-ignore
        const pipe: Writable = this.serverProcess!.stdio[3]!;
        pipe.write(JSON.stringify(message) + "\n");
    }

    private clearBacklog() {
        if (this.serverProcess === undefined) {
            return;
        }
        for (const message of this.backlog) {
            this.writeMessage(message);
        }
        this.backlog = [];
    }

    public sendMessage(message: StreamMessage) {
        if (this.serverProcess === undefined) {
            this.backlog.push(message);
        } else {
            this.clearBacklog();
            this.writeMessage(message);
        }
    }
}

export const server = new Server();
