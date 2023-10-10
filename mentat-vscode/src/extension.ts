import * as vscode from "vscode"

// import { WebviewProvider } from "./webviews/utils/provider";

export function activate(context: vscode.ExtensionContext) {
  console.log('Congratulations, your extension "helloworld-sample" is now active!')

  context.subscriptions.push(
    vscode.commands.registerCommand("mentat.helloWorld", () => {
      vscode.window.showInformationMessage("Hello world!!")
    })
  )

  // const chatWebviewProvider = new WebviewProvider("chat", context.extensionUri);
  // context.subscriptions.push(
  //   vscode.window.registerWebviewViewProvider("MentatChat", chatWebviewProvider, {
  //     webviewOptions: { retainContextWhenHidden: true },
  //   })
  // );
}
