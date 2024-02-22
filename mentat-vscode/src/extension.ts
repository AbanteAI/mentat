import WebviewProvider from "lib/WebviewProvider";
import { setupServer } from "utils/setup";
import * as vscode from "vscode";

async function activateClient(context: vscode.ExtensionContext) {
    try {
        const server = await setupServer();
        const chatWebviewProvider = new WebviewProvider(
            context.extensionUri,
            server
        );
        context.subscriptions.push(
            vscode.window.registerWebviewViewProvider(
                "Mentat",
                chatWebviewProvider,
                {
                    webviewOptions: { retainContextWhenHidden: true },
                }
            )
        );
    } catch (e) {
        vscode.window.showErrorMessage(
            `${
                (e as any).message
            }\nEnsure that python 3.10 or higher is available on your machine.`,
            "Close"
        );
        throw e;
    }
}

export function activate(context: vscode.ExtensionContext) {
    activateClient(context);
}

export function deactivate() {
    // TODO: Stop mentat language server
}
