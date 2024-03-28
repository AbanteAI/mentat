import path from "path";
import { FileEdit } from "types";
import * as vscode from "vscode";
import { excludeResource, includeResource } from "./commands";

async function renameFile(fileEdit: FileEdit) {
    if (fileEdit.new_file_path) {
        const workspaceEdit = new vscode.WorkspaceEdit();
        workspaceEdit.renameFile(
            vscode.Uri.file(fileEdit.file_path),
            vscode.Uri.file(fileEdit.new_file_path)
        );
        excludeResource({ path: fileEdit.file_path });
        await vscode.workspace.applyEdit(workspaceEdit);
        includeResource({ path: fileEdit.new_file_path });
    }
}

export async function acceptEdit(fileEdit: FileEdit) {
    if (fileEdit.type == "deletion") {
        const workspaceEdit = new vscode.WorkspaceEdit();
        workspaceEdit.deleteFile(vscode.Uri.file(fileEdit.file_path));
        excludeResource({ path: fileEdit.file_path });
        await vscode.workspace.applyEdit(workspaceEdit);
        return;
    }
    if (fileEdit.type == "creation") {
        const workspaceEdit = new vscode.WorkspaceEdit();
        workspaceEdit.createFile(vscode.Uri.file(fileEdit.file_path));
        await vscode.workspace.applyEdit(workspaceEdit);
        includeResource({ path: fileEdit.file_path });
    }

    await renameFile(fileEdit);
    const filePath = fileEdit.new_file_path ?? fileEdit.file_path;

    const editor = await vscode.window.showTextDocument(
        vscode.Uri.file(filePath)
    );

    editor.edit((editBuilder) => {
        editBuilder.replace(
            new vscode.Range(0, 0, editor.document.lineCount + 1, 0),
            fileEdit.new_content
        );
    });
    await editor.document.save();
}

export async function previewEdit(fileEdit: FileEdit) {
    await renameFile(fileEdit);
    const filePath = fileEdit.new_file_path ?? fileEdit.file_path;

    const editor = await vscode.window.showTextDocument(
        vscode.Uri.file(filePath)
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
            path: filePath,
            fragment: previousContent,
        }),
        vscode.Uri.file(filePath),
        `${path.basename(filePath)} (Suggested Changes)`
    );
}
