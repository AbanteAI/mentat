import { LanguageClientMessage } from "types";
import * as vscode from "vscode";
import { Uri, Webview } from "vscode";
import { LanguageClient } from "vscode-languageclient/node";

import { MentatClient } from "./client";

/**
 * A helper function that returns a unique alphanumeric identifier called a nonce.
 *
 * @remarks This function is primarily used to help enforce content security
 * policies for resources/scripts being executed in a webview context.
 *
 * @returns A nonce
 */
function getNonce() {
  let text = "";
  const possible = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";
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
  private mentatClient: MentatClient;
  private view?: vscode.WebviewView;
  private doc?: vscode.TextDocument;

  constructor(extensionUri: vscode.Uri, mentatClient: MentatClient) {
    this.extensionUri = extensionUri;
    this.mentatClient = mentatClient;
  }

  // Posts a message to the webview view.
  //  endpoint: The endpoint to send the message to.
  //  message: The message to send.
  //  Throws an error if the view is not available.
  // notice: the only things being posted to the webviews are state objects, so this will be a private function
  private postMessage(endpoint: string, message: any) {
    if (!this.view) {
      console.log("postMessage to: ", endpoint);
      console.log("with message: ", message);
      console.error(`No view available. Its possibly collapsed`);
    } else {
      this.view.webview.postMessage({ type: endpoint, data: message });
    }
  }

  private getHtmlForWebview(webview: vscode.Webview) {
    const scriptUri = getUri(webview, this.extensionUri, [
      "build",
      "webview",
      "index.js",
    ]);

    const styleUri = getUri(webview, this.extensionUri, [
      "build",
      "webview",
      "main.css",
    ]);

    const nonce = getNonce();

    const html = `
      <!DOCTYPE html>
      <html lang="en">
        <head>
          <meta charset="UTF-8" />
          <meta name="viewport" content="width=device-width, initial-scale=1.0" />
          <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src ${webview.cspSource} 'nonce-${nonce}'; font-src ${webview.cspSource}; script-src 'nonce-${nonce}';">
          <link nonce="${nonce}" rel="stylesheet" type="text/css" href="${styleUri}">
          <title>Mentat</title>
        </head>
        <body>
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

    webviewView.webview.options = {
      enableScripts: true,
      localResourceRoots: [this.extensionUri],
    };
    webviewView.webview.html = this.getHtmlForWebview(webviewView.webview);

    webviewView.webview.onDidReceiveMessage(async (message: LanguageClientMessage) => {
      console.log(`Extension received message: ${message}`);

      this.mentatClient.sendChatMessage(message.data);
    });
  }
}

export { WebviewProvider };
