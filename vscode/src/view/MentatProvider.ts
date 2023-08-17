import * as vscode from 'vscode';
import { traceError, traceLog, traceVerbose } from '../common/log/logging';

class MentatProvider implements vscode.WebviewViewProvider {
    private _view?: vscode.WebviewView;
    public static readonly viewType = 'mentat.chatView';

    constructor(private readonly _extensionUri: vscode.Uri) {
        
    }

    public resolveWebviewView(
        webviewView: vscode.WebviewView,
        context: vscode.WebviewViewResolveContext,
        _token: vscode.CancellationToken,
    ) {
        this._view = webviewView;

        webviewView.webview.options = {
            enableScripts: true,
            localResourceRoots: [this._extensionUri],
        };

        webviewView.webview.html = this._generateHtml(webviewView.webview);

        // Intercept messages coming from the webview/user
        this._view.webview.onDidReceiveMessage((data) => {
            if (data.type === 'message') {
                if (!this._view) {
                    traceError('Webview not found.');
                    return;
                }
                // Add the prompt to conversation
                this._view.webview.postMessage(data.data);
                // TODO: Send to backend
                this._view.webview.postMessage({ type: 'system', value: 'Message received by MentatProvider.' });
            
            } else if (data.type === 'action') {
                const { value } = data.data;
                traceLog(`Action: ${value}`);
            }
        });
    }

    private _generateHtml(webview: vscode.Webview) {

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

    private _getUri(webview: vscode.Webview, ...paths: string[]) {
        return webview.asWebviewUri(vscode.Uri.joinPath(this._extensionUri, ...paths));
    }
}

export { MentatProvider };
