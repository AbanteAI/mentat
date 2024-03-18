import * as vscode from "vscode";
import { server } from "./server";
import { FileEdit } from "types";
import path from "path";
import WebviewProvider from "lib/WebviewProvider";

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

export function clearChat(...args: any[]) {
    server.sendStreamMessage(null, "clear_conversation");
}

export function eraseChatHistory(
    webviewProvider: WebviewProvider
): (...args: any[]) => void {
    return (...args: any[]) => {
        webviewProvider.sendMessage(null, "vscode:eraseChatHistory");
    };
}

export async function acceptEdit(fileEdit: FileEdit) {
    const editor = await vscode.window.showTextDocument(
        vscode.Uri.file(fileEdit.file_path)
    );

    editor.edit((editBuilder) => {
        editBuilder.replace(
            new vscode.Range(0, 0, editor.document.lineCount + 1, 0),
            fileEdit.new_content
        );
    });
}

export async function previewEdit(fileEdit: FileEdit) {
    // TODO: Decide if we want default all selected or none selected (also, when we do, stop from opening both the file and the diff)
    // The reason we default to all selected right now is because vscode's diff viewer shows green on the right and red on the left
    const editor = await vscode.window.showTextDocument(
        vscode.Uri.file(fileEdit.file_path)
    );

    const previousContent = editor.document.getText();
    editor.edit((editBuilder) => {
        editBuilder.replace(
            new vscode.Range(0, 0, editor.document.lineCount + 1, 0),
            fileEdit.new_content
        );
    });

    vscode.commands.executeCommand(
        "vscode.diff",
        vscode.Uri.from({
            scheme: "mentat",
            path: fileEdit.file_path,
            fragment: previousContent,
        }),
        vscode.Uri.file(fileEdit.file_path),
        `${path.basename(fileEdit.file_path)} (Suggested Changes)`
    );
}
