import { ChildProcessWithoutNullStreams } from "child_process";
import WebviewProvider from "lib/WebviewProvider";
import { setupServer } from "utils/setup";
import * as vscode from "vscode";

var serverProcess: ChildProcessWithoutNullStreams | undefined = undefined;

async function activateClient(context: vscode.ExtensionContext) {
    try {
        serverProcess = await setupServer();
        const chatWebviewProvider = new WebviewProvider(
            context.extensionUri,
            serverProcess
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
