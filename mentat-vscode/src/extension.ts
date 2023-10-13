import * as vscode from "vscode";

import { installMentat } from "./setup";
import { WebviewProvider } from "./webview-provider";

export function activate(context: vscode.ExtensionContext) {
  const buildServer = async (
    progress: vscode.Progress<{ message?: string; increment?: number }>
  ) => {
    try {
      await installMentat(progress);
      // const options = await tryResolveServerOptions(progress, port);
      // if (options) {
      //   onServerOptionsResolved(options);
      // } else {
      //   throw Error("Build failed or not started. Is AutoStart enabled?");
      // }
    } catch (e) {
      vscode.window.showErrorMessage(
        `${(e as any).message
        }\nEnsure that python3.10 is available and try installing Mentat manually: https://github.com/AbanteAI/mentat`,
        "Close"
      );
      throw e;
    }
  };

  vscode.commands.registerCommand("mentat.build-server", () => {
    vscode.window.withProgress(
      { location: vscode.ProgressLocation.Notification },
      async (progress) => {
        return buildServer(progress);
      }
    );
  });

  context.subscriptions.push(
    vscode.commands.registerCommand("what's happening here?", () => {
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
