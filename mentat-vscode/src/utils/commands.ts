import * as vscode from "vscode";
import { server } from "./server";
import WebviewProvider from "lib/WebviewProvider";

function getFilepath(args: any[]): string | undefined {
    return (
        args.at(0)?.fsPath ?? vscode.window.activeTextEditor?.document?.fileName
    );
}

export function includeResource(...args: any[]) {
    const filePath = getFilepath(args);
    if (filePath === undefined) {
        return;
    }
    server.sendStreamMessage(filePath, "include");
}

export function excludeResource(...args: any[]) {
    const filePath = getFilepath(args);
    if (filePath === undefined) {
        return;
    }
    server.sendStreamMessage(filePath, "exclude");
}

export function clearChatbox(
    webviewProvider: WebviewProvider
): (...args: any[]) => void {
    return (...args: any[]) => {
        webviewProvider.sendMessage(null, "vscode:clearChatbox");
    };
}
