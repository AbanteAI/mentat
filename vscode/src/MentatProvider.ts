import * as path from 'path';
import * as fs from 'fs';
import * as vscode from 'vscode';
import { traceError, traceLog, traceVerbose } from './common/log/logging';
import { LanguageClient } from 'vscode-languageclient/node';
import { Command, OutboundMessage, Sender, InboundMessage } from './types/globals';

export class MentatProvider implements vscode.WebviewViewProvider {
    private _view?: vscode.WebviewView;
    public static readonly viewType = 'mentat.chatView';

    constructor(
        private readonly _extensionUri: vscode.Uri,
        private _extensionPath: string,
        private readonly _serverName: string,
        private readonly _serverId: string,
    ) {}

    /**
     * Called when our view is first initialized
     * @param webviewView
     * @param context
     * @param _token
     * @returns
     */
    public resolveWebviewView(
        webviewView: vscode.WebviewView,
        _context: vscode.WebviewViewResolveContext,
        _token: vscode.CancellationToken,
    ): void | Thenable<void> {
        this._view = webviewView;

        webviewView.webview.options = {
            enableScripts: true,
            localResourceRoots: [this._extensionUri],
        };

        webviewView.webview.html = this._generateHtml(webviewView.webview);

        // Intercept messages coming from the webview/user
        this._view.webview.onDidReceiveMessage(async (msg: OutboundMessage) => {
            const { command, data } = msg;
            switch (command) {
                case Command.getPaths:
                    // Resolve the list of files in the workspace
                    let paths: any[] = [];
                    if (vscode.workspace.workspaceFolders) {
                        const workspaceFolder = vscode.workspace.workspaceFolders[0];
                        const uri = workspaceFolder.uri;
                        const files = await vscode.workspace.fs.readDirectory(uri);
                        paths = files.filter(([_, type]) => type === vscode.FileType.File).map(([name]) => name);
                    }
                    this._view?.webview.postMessage({ type: 'paths', value: paths });
                    break;
                case Command.getResponse:
                    const echo = { type: 'user', value: data };
                    this._view?.webview.postMessage(echo);
                    // Send to backend
                    vscode.commands.executeCommand(`${this._serverId}.${Command.getResponse}`, data);
                    // Ignore the return value for now because response is streamed
                    break;
                case Command.interrupt:
                    vscode.commands.executeCommand(`${this._serverId}.${Command.interrupt}`);
                    break;
                case Command.restart:
                    vscode.commands.executeCommand(`${this._serverId}.${Command.restart}`, data);
                    break;
                default:
                    traceLog(`Unknown command: ${command}`);
                    break;
            }
        });
    }

    /**
     * Generates the HTML content for the webview.
     * @param webview
     * @returns The HTML string
     */
    private _generateHtml(webview: vscode.Webview): string {
        const indexPath = path.join(this._extensionPath, 'dist', 'index.html');
        let htmlContent = fs.readFileSync(indexPath, 'utf-8');

        // Replace relative paths with webview URIs
        const scriptUri = this._getUri(webview, 'dist', 'bundle.js');
        const stylesUri = this._getUri(webview, 'dist', 'bundle.css');
        htmlContent = htmlContent.replace('/bundle.js', scriptUri.toString());
        htmlContent = htmlContent.replace('/bundle.css', stylesUri.toString());

        return htmlContent;
    }

    /**
     * Get the URI of a file
     * @param webview
     * @param paths - relative path from the 'mentat/vscode' folder
     * @returns - The URI
     */
    private _getUri(webview: vscode.Webview, ...paths: string[]): vscode.Uri {
        return webview.asWebviewUri(vscode.Uri.joinPath(this._extensionUri, ...paths));
    }

    /**
     * Register the language client to stream chunks of data to the webview
     * @param lsClient - The language client
     * @returns
     */
    public registerClient(lsClient: LanguageClient | undefined) {
        if (!lsClient) {
            traceError('Language client not found');
            return;
        }
        lsClient.onNotification('mentat.sendChunk', (data: String) => {
            const msg = { type: Sender.assistant, value: data };
            this._view?.webview.postMessage(msg);
        });
    }
}
