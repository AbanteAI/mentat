import * as vscode from "vscode";

import { WebviewProvider } from "./webviews/utils/provider";

function createChatWebview(context: vscode.ExtensionContext) {
  const chatWebviewProvider = new WebviewProvider("chat", context.extensionUri);
  context.subscriptions.push(
    vscode.window.registerWebviewViewProvider("MentatChat", chatWebviewProvider, {
      webviewOptions: { retainContextWhenHidden: true },
    })
  );
}

export function activate(context: vscode.ExtensionContext) {
  console.log('Congratulations, your extension "helloworld-sample" is now active!');

  // The command has been defined in the package.json file
  // Now provide the implementation of the command with registerCommand
  // The commandId parameter must match the command field in package.json

  context.subscriptions.push(
    vscode.commands.registerCommand("extension.helloWorld", () => {
      vscode.window.showInformationMessage("Hello World!");
    }),
    vscode.commands.registerCommand("extension.startChat", createChatWebview)
  );
}
