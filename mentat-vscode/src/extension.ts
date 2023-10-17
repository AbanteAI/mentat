import * as vscode from "vscode";

import { MentatClient } from "./client";
import { getLanguageServerOptions, installMentat } from "./setup";
import { WebviewProvider } from "./webview-provider";

export function activate(context: vscode.ExtensionContext) {
  async function buildServer(
    progress: vscode.Progress<{ message?: string; increment?: number }>
  ) {
    try {
      await installMentat(progress);
      const options = await getLanguageServerOptions(8080);

      const mentatClient = new MentatClient(context, options);
      await mentatClient.startLanguageClient();

      const chatWebviewProvider = new WebviewProvider(
        context.extensionUri,
        mentatClient
      );

      context.subscriptions.push(
        vscode.window.registerWebviewViewProvider("MentatChat", chatWebviewProvider, {
          webviewOptions: { retainContextWhenHidden: true },
        })
      );
    } catch (e) {
      vscode.window.showErrorMessage(
        `${(e as any).message
        }\nEnsure that python3.10 is available and try installing Mentat manually: https://github.com/AbanteAI/mentat`,
        "Close"
      );
      throw e;
    }
  }

  // Manually (re)build the Mentat language server
  vscode.commands.registerCommand("mentat.build-server", () => {
    vscode.window.withProgress(
      { location: vscode.ProgressLocation.Notification },
      async (progress) => {
        buildServer(progress);
      }
    );
  });

  vscode.window.withProgress(
    { location: vscode.ProgressLocation.Notification },
    async (progress) => {
      buildServer(progress);
    }
  );

  context.subscriptions.push(
    vscode.commands.registerCommand("what's happening here?", () => {
      vscode.window.showInformationMessage("Hello world!!");
    })
  );
}
