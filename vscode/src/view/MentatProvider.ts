import * as vscode from 'vscode';
import { traceError, traceLog, traceVerbose } from '../common/log/logging';

export interface WebViewMessage {
    command: Command,
    data: string | undefined,
}

export enum Command {
    getResponse = 'getResponse',
    interrupt = 'interrupt',
    restart = 'restart',
}

export class MentatProvider implements vscode.WebviewViewProvider {
    private _view?: vscode.WebviewView;
    public static readonly viewType = 'mentat.chatView';

    constructor(
      private readonly _extensionUri: vscode.Uri, 
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
        context: vscode.WebviewViewResolveContext,
        _token: vscode.CancellationToken,
    ): void | Thenable<void> {
        this._view = webviewView;

        webviewView.webview.options = {
            enableScripts: true,
            localResourceRoots: [this._extensionUri],
        };

        webviewView.webview.html = this._generateHtml(webviewView.webview);

        // Intercept messages coming from the webview/user
        this._view.webview.onDidReceiveMessage((msg: WebViewMessage) => {
            const { command, data } = msg;
            switch (command) {
                case Command.getResponse:
                    const echo = { type: "user", value: data };
                    this._view?.webview.postMessage(echo);
                    // Send to backend
                    vscode.commands.executeCommand(`${this._serverId}.${Command.getResponse}`, data)
                        .then((response) => {
                            const msg = { type: "assistant", value: response };
                            this._view?.webview.postMessage(msg);
                        });
                    break;
                case Command.interrupt:
                    vscode.commands.executeCommand(`${this._serverId}.${Command.interrupt}`)
                        .then((response) => {
                            const msg = { type: "system", value: response };
                            this._view?.webview.postMessage(msg);
                        });
                    break;
                case Command.restart:
                    vscode.commands.executeCommand(`${this._serverId}.${Command.restart}`)
                        .then((response) => {
                            const msg = { type: "system", value: response };
                            this._view?.webview.postMessage(msg);
                        });
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

        // Load scripts and styles files
        const scriptUri = this._getUri(webview, 'src', 'view', 'scripts', 'main.js');
        const stylesUri = this._getUri(webview, 'src', 'view', 'css', 'styles.css');
        
        return `
          <!DOCTYPE html>
            <html lang="en">
            <head>
              <meta charset="UTF-8">
              <meta name="viewport" content="width=device-width, initial-scale=1.0">
              <link href="${stylesUri}" rel="stylesheet">
            </head>
            <body>
            
            <div id="conversation-container" class="conversation">
              <div class="message assistant">Welcome to Mentat Chat!</div>
            </div>

            <input class="input" id="prompt" type="text" placeholder="Enter a prompt" />
            <div class="button-container">
              <button class="button" id="get-response">Get Response</button>
              <button class="button" id="interrupt">Interrupt</button>
              <button class="button" id="restart">Restart</button>
            </div>

            <script src="${scriptUri}"></script>
            </body>
          </html>
        `;
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
}