import MentatClient from "MentatClient"
import WebviewProvider from "WebviewProvider"
import { getLanguageServerOptions, installMentat } from "utils/setup"
import * as vscode from "vscode"

async function buildServer(
  context: vscode.ExtensionContext,
  progress: vscode.Progress<{ message?: string; increment?: number }>
) {
  try {
    // await installMentat(progress);
    const options = await getLanguageServerOptions(7798)

    const mentatClient = new MentatClient(context, options)
    mentatClient.startLanguageClient()

    // const chatWebviewProvider = new WebviewProvider(context.extensionUri, mentatClient);

    // context.subscriptions.push(
    //   vscode.window.registerWebviewViewProvider("MentatChat", chatWebviewProvider, {
    //     webviewOptions: { retainContextWhenHidden: true },
    //   })
    // );
  } catch (e) {
    vscode.window.showErrorMessage(
      `${
        (e as any).message
      }\nEnsure that python3.10 is available and try installing Mentat manually: https://github.com/AbanteAI/mentat`,
      "Close"
    )
    throw e
  }
}

export function activate(context: vscode.ExtensionContext) {
  // Register commands
  vscode.commands.registerCommand("mentat.build-server", () => {
    vscode.window.withProgress(
      { location: vscode.ProgressLocation.Notification },
      async (progress) => {
        buildServer(context, progress)
      }
    )
  })

  // Build server
  vscode.window.withProgress(
    { location: vscode.ProgressLocation.Notification },
    async (progress) => {
      buildServer(context, progress)
    }
  )
}
