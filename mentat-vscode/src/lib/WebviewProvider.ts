import { ChildProcessWithoutNullStreams } from "child_process";
import { StreamMessage } from "types";
import { server } from "utils/server";
import * as vscode from "vscode";
import { Uri, Webview } from "vscode";

function getNonce() {
    let text = "";
    const possible =
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";
    for (let i = 0; i < 32; i++) {
        text += possible.charAt(Math.floor(Math.random() * possible.length));
    }
    return text;
}

function getUri(webview: Webview, extensionUri: Uri, pathList: string[]) {
    return webview.asWebviewUri(Uri.joinPath(extensionUri, ...pathList));
}

class WebviewProvider implements vscode.WebviewViewProvider {
    private extensionUri: vscode.Uri;
    private view?: vscode.WebviewView;

    constructor(extensionUri: vscode.Uri) {
        this.extensionUri = extensionUri;
    }

    // Send LS Messages to the WebView
    public postMessage(message: StreamMessage) {
        if (!this.view) {
            console.error(`No view available. It has possibly collapsed`);
        } else {
            this.view.webview.postMessage(message);
        }
    }

    private getHtmlForWebview() {
        if (this.view === undefined) {
            throw Error("Webview View is undefined");
        }

        const scriptUri = getUri(this.view.webview, this.extensionUri, [
            "build",
            "webviews",
            "index.js",
        ]);

        // TODO: Can this be done in react code? Check
        const styleUri = getUri(this.view.webview, this.extensionUri, [
            "build",
            "webviews",
            "main.css",
        ]);

        const nonce = getNonce();
        const html = `
          <!DOCTYPE html>
          <html lang="en">
            <head>
              <meta charset="UTF-8" />
              <meta name="viewport" content="width=device-width, initial-scale=1.0" />
              <meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src ${this.view.webview.cspSource} 'nonce-${nonce}'; font-src ${this.view.webview.cspSource}; script-src 'nonce-${nonce}';">
              <link nonce="${nonce}" rel="stylesheet" type="text/css" href="${styleUri}">
              <title>Mentat</title>
            </head>
            <body class="webview-body">
              <div id="root"></div>
              <script nonce="${nonce}" src="${scriptUri}"></script>
            </body>
          </html>
        `;
        return html;
    }

    public resolveWebviewView(
        webviewView: vscode.WebviewView,
        _context: vscode.WebviewViewResolveContext,
        _token: vscode.CancellationToken
    ) {
        this.view = webviewView;

        this.view.webview.options = {
            enableScripts: true,
            localResourceRoots: [this.extensionUri],
        };
        this.view.webview.html = this.getHtmlForWebview();

        // Send messages from React app to server
        this.view.webview.onDidReceiveMessage((message: StreamMessage) =>
            server.sendMessage(message)
        );

        // Send messages from server to React app
        server.messageEmitter.on("message", (message: StreamMessage) =>
            this.postMessage(message)
        );
    }
}

export default WebviewProvider;
