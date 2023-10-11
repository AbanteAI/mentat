import * as vscode from "vscode";

import { WebviewProvider } from "./webview-provider";

export function activate(context: vscode.ExtensionContext) {
  console.log('Congratulations, your extension "helloworld-sample" is now active!');

  context.subscriptions.push(
    vscode.commands.registerCommand("mentat.helloWorld", () => {
      vscode.window.showInformationMessage("Hello world!!");
    })
  );

  const chatWebviewProvider = new WebviewProvider(context.extensionUri);
  context.subscriptions.push(
    vscode.window.registerWebviewViewProvider("MentatChat", chatWebviewProvider, {
      webviewOptions: { retainContextWhenHidden: true },
    })
  );
}
