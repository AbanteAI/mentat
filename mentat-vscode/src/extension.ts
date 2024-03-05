import WebviewProvider from "lib/WebviewProvider";
import * as vscode from "vscode";
import * as os from "os";
import { excludeResource, includeResource } from "utils/commands";
import { ContextUpdateData, StreamMessage } from "types";
import path from "path";
import { server } from "utils/server";

function contextUpdate(data: ContextUpdateData) {
    const features = [...data.features, ...data.auto_features];
    vscode.commands.executeCommand(
        "setContext",
        "mentat.includedFiles",
        features
    );
    const folders: string[] = [];
    for (const feature of features) {
        var dir = feature;
        while (dir !== path.dirname(dir)) {
            dir = path.dirname(dir);
            folders.push(dir);
        }
    }
    vscode.commands.executeCommand(
        "setContext",
        "mentat.includedFolders",
        folders
    );
}

async function activateClient(context: vscode.ExtensionContext) {
    try {
        // vscode.window.registerFileDecorationProvider()

        // In package.json:
        // {
        //    "id": "context-view",
        //    "name": "Context"
        // },
        // const contextProvider = new ContextProvider(workspaceRoot);
        // context.subscriptions.push(vscode.window.registerTreeDataProvider("context-view", contextProvider));

        const chatWebviewProvider = new WebviewProvider(context.extensionUri);
        context.subscriptions.push(
            vscode.window.registerWebviewViewProvider(
                "mentat-webview",
                chatWebviewProvider,
                {
                    webviewOptions: { retainContextWhenHidden: true },
                }
            )
        );

        const workspaceRoot =
            vscode.workspace.workspaceFolders?.at(0)?.uri?.path ?? os.homedir();
        await server.startServer(workspaceRoot);

        context.subscriptions.push(
            vscode.commands.registerCommand(
                "mentat.includeFile",
                includeResource
            )
        );
        context.subscriptions.push(
            vscode.commands.registerCommand(
                "mentat.includeFolder",
                includeResource
            )
        );
        context.subscriptions.push(
            vscode.commands.registerCommand(
                "mentat.excludeFile",
                excludeResource
            )
        );
        context.subscriptions.push(
            vscode.commands.registerCommand(
                "mentat.excludeFolder",
                excludeResource
            )
        );

        server.messageEmitter.on("message", (message: StreamMessage) => {
            switch (message.channel) {
                case "context_update": {
                    contextUpdate(message.data);
                    break;
                }
            }
        });
    } catch (e) {
        vscode.window.showErrorMessage((e as any).message, "Close");
        throw e;
    }
}

export function activate(context: vscode.ExtensionContext) {
    activateClient(context);
}

export function deactivate() {
    server.closeServer();
}
