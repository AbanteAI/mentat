import * as vscode from "vscode";

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

class WebviewProvider implements vscode.WebviewViewProvider {
  private extensionUri: vscode.Uri;
  private view?: vscode.WebviewView;
  private doc?: vscode.TextDocument;

  constructor(extensionUri: vscode.Uri) {
    this.extensionUri = extensionUri;
  }

  private getHtmlForWebview(webview: vscode.Webview) {
    console.log("GETTING HTML");

    const scriptUri = webview.asWebviewUri(
      vscode.Uri.joinPath(this.extensionUri, "build/webview/index.js")
    );

    // Use a nonce to only allow specific scripts to be run
    const nonce = getNonce();

    // const temp = `
    //   <!DOCTYPE html>
    //   <html lang="en">
    //     <head>
    //       <meta charset="UTF-8" />
    //       <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    //       <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src ${webview.cspSource} 'nonce-${nonce}'; font-src ${webview.cspSource}; script-src 'nonce-${nonce}';">
    //       <link rel="stylesheet" type="text/css" href="${stylesUri}">
    //       <title>Component Gallery (React)</title>
    //       <style nonce="${nonce}">
    //         @font-face {
    //           font-family: "codicon";
    //           font-display: block;
    //           src: url("${codiconFontUri}") format("truetype");
    //         }
    //       </style>
    //     </head>
    //     <body>
    //       <div id="root"></div>
    //       <script type="module" nonce="${nonce}" src="${scriptUri}"></script>
    //     </body>
    //   </html>
    // `;

    const html = `
      <!DOCTYPE html>
      <html lang="en">
        <head>
          <meta charset="UTF-8" />
          <meta name="viewport" content="width=device-width, initial-scale=1.0" />
          <title>Mentat</title>
        </head>
        <body>
          <div id="root"></div>
          <script type="module" nonce="${nonce}" src="${scriptUri}"></script>
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
    console.log("RESOLVING WEBVIEW");

    webviewView.webview.options = {
      enableScripts: true,
      localResourceRoots: [this.extensionUri],
    };
    webviewView.webview.html = this.getHtmlForWebview(webviewView.webview);

    // this.view.webview.options = {
    //   enableScripts: true,
    //   localResourceRoots: [this.extensionUri],
    // };
    // this.view.webview.html = this.getHtmlForWebview(this.view.webview);

    console.log("RESOLVED WEBVIEW");
  }
}

export { WebviewProvider };
