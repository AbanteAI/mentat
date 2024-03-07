import * as vscode from "vscode";
import { server } from "./server";

function getFilepath(args: any[]): string | undefined {
    return (
        args.at(0)?.path ?? vscode.window.activeTextEditor?.document?.fileName
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
