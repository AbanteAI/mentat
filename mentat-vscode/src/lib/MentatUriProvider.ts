import * as vscode from "vscode";

export class MentatUriProvider implements vscode.TextDocumentContentProvider {
    onDidChangeEmitter = new vscode.EventEmitter<vscode.Uri>();
    onDidChange = this.onDidChangeEmitter.event;

    provideTextDocumentContent(
        uri: vscode.Uri,
        token: vscode.CancellationToken
    ): string {
        return uri.fragment;
    }
}
