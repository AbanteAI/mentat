import { ChildProcess } from "child_process";
import WebviewProvider from "lib/WebviewProvider";
import { Socket } from "net";
import { setupServer } from "utils/setup";
import * as vscode from "vscode";

var serverSocket: Socket | undefined = undefined;
var serverProcess: ChildProcess | undefined = undefined;

async function activateClient(context: vscode.ExtensionContext) {
    try {
        [serverSocket, serverProcess] = await setupServer();
        const chatWebviewProvider = new WebviewProvider(
            context.extensionUri,
            serverSocket
        );
        context.subscriptions.push(
            vscode.window.registerWebviewViewProvider(
                "MentatChat",
                chatWebviewProvider,
                {
                    webviewOptions: { retainContextWhenHidden: true },
                }
            )
        );
    } catch (e) {
        vscode.window.showErrorMessage((e as any).message, "Close");
        throw e;
    }
}

export function activate(context: vscode.ExtensionContext) {
    activateClient(context);
}

export function deactivate() {
    if (serverProcess !== undefined) {
        serverProcess.kill();
    }
}
