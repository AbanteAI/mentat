import MentatClient from "MentatClient";
import emitter from "emitter";
import {
  LanguageClientMessage,
  LanguageServerMethod,
  LanguageServerNotification,
  LanguageServerRequest,
} from "types";
import * as vscode from "vscode";
import { Uri, Webview } from "vscode";

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

  constructor(extensionUri: vscode.Uri, mentatClient: MentatClient) {
    this.extensionUri = extensionUri;
    this.mentatClient = mentatClient;
  }

  // Send LS Messages to the WebView
  private postMessage(
    method: LanguageServerMethod,
    message: LanguageServerRequest | LanguageServerNotification
  ) {
    if (!this.view) {
      console.log("postMessage to: ", method);
      console.log("with message: ", message);
      console.error(`No view available. Its possibly collapsed`);
    } else {
      this.view.webview.postMessage({ method: method, data: message });
    }
  }

  private setHtmlForWebview() {
    if (this.view === undefined) {
      throw Error("Webview View is undefined");
    }

    const scriptUri = getUri(this.view.webview, this.extensionUri, [
      "build",
      "webview",
      "index.js",
    ]);

    const styleUri = getUri(this.view.webview, this.extensionUri, [
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
          <meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src ${this.view.webview.cspSource} 'nonce-${nonce}'; font-src ${this.view.webview.cspSource}; script-src 'nonce-${nonce}';">
          <link nonce="${nonce}" rel="stylesheet" type="text/css" href="${styleUri}">
          <title>Mentat</title>
        </head>
        <body>
          <div id="root"></div>
          <script nonce="${nonce}" src="${scriptUri}"></script>
        </body>
      </html>
    `;

    this.view.webview.html = html;
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
    this.setHtmlForWebview();

    // Handle messages from the webview (and send to MentatClient)
    this.view.webview.onDidReceiveMessage(async (message: LanguageClientMessage) => {
      console.log(`Extension received message from Webview: ${message}`);
      switch (message.method) {
        case LanguageServerMethod.CreateSession:
          this.mentatClient.handleCreateSession();
          break;
        case LanguageServerMethod.GetInput:
          this.mentatClient.handleGetInput(message);
          break;
        default:
          console.log(`Webview received unhandled method ${message.method}`);
      }
    });

    // Handle messages from the MentatClient (and send to webview)
    emitter.on(LanguageServerMethod.GetInput, (message: LanguageServerRequest) => {
      this.postMessage(LanguageServerMethod.GetInput, message);
    });
    emitter.on(LanguageServerMethod.StreamSession, (message: LanguageServerRequest) => {
      this.postMessage(LanguageServerMethod.StreamSession, message);
    });
  }
}

export default WebviewProvider;
