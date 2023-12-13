import emitter from "utils/emitter"
import { LanguageServerMessage } from "types"
import * as vscode from "vscode"
import { Uri, Webview } from "vscode"

import { LanguageClient } from "vscode-languageclient/node"

/**
 * A helper function that returns a unique alphanumeric identifier called a nonce.
 *
 * @remarks This function is primarily used to help enforce content security
 * policies for resources/scripts being executed in a webview context.
 *
 * @returns A nonce
 */
function getNonce() {
  let text = ""
  const possible = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
  for (let i = 0; i < 32; i++) {
    text += possible.charAt(Math.floor(Math.random() * possible.length))
  }
  return text
}

function getUri(webview: Webview, extensionUri: Uri, pathList: string[]) {
  return webview.asWebviewUri(Uri.joinPath(extensionUri, ...pathList))
}

class WebviewProvider implements vscode.WebviewViewProvider {
  private extensionUri: vscode.Uri
  private languageClient: LanguageClient
  private view?: vscode.WebviewView

  constructor(extensionUri: vscode.Uri, languageClient: LanguageClient) {
    this.extensionUri = extensionUri
    this.languageClient = languageClient
  }

  // Send LS Messages to the WebView
  private postMessage(message: LanguageServerMessage) {
    console.log(`Extension sending message to Webview: ${message}`)
    if (!this.view) {
      console.error(`No view available. Its possibly collapsed`)
    } else {
      this.view.webview.postMessage(message)
    }
  }

  private setHtmlForWebview() {
    if (this.view === undefined) {
      throw Error("Webview View is undefined")
    }

    const scriptUri = getUri(this.view.webview, this.extensionUri, [
      "build",
      "webviews",
      "index.js",
    ])

    const styleUri = getUri(this.view.webview, this.extensionUri, [
      "build",
      "webviews",
      "main.css",
    ])

    const nonce = getNonce()

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
    `

    this.view.webview.html = html
  }

  public resolveWebviewView(
    webviewView: vscode.WebviewView,
    _context: vscode.WebviewViewResolveContext,
    _token: vscode.CancellationToken
  ) {
    this.view = webviewView

    this.view.webview.options = {
      enableScripts: true,
      localResourceRoots: [this.extensionUri],
    }
    this.setHtmlForWebview()

    this.view.webview.onDidReceiveMessage(async (message: LanguageServerMessage) => {
      console.log(`WebviewProvider received message from Webview: ${message}`)
      switch (message.type) {
        case "request": {
          const response: string = await this.languageClient.sendRequest(
            message.method,
            message
          )
          console.log(`WebviewProvider got response from LanguageServer: ${response}`)
          const responseMessage: LanguageServerMessage = {
            type: "request",
            method: message.method,
            data: response,
          }
          this.postMessage(responseMessage)
          break
        }
        default: {
          throw Error(`Unhandled message type: ${message.type}`)
        }
      }
    })

    // // Handle messages from the LanguageServer and send to Webview
    // emitter.on(LanguageServerMethod.GetInput, (message: LanguageServerRequest) => {
    //   this.postMessage(LanguageServerMethod.GetInput, message)
    // })
    // emitter.on(LanguageServerMethod.StreamSession, (message: LanguageServerRequest) => {
    //   this.postMessage(LanguageServerMethod.StreamSession, message)
    // })
    // emitter.on(LanguageServerMethod.EchoInput, (message: LanguageServerRequest) => {
    //   this.postMessage(LanguageServerMethod.EchoInput, message)
    // })
  }
}

export default WebviewProvider
