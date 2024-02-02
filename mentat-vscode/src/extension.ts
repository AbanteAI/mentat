import WebviewProvider from "lib/WebviewProvider"
import { getLanguageServerOptions, installMentat } from "utils/setup"
import * as vscode from "vscode"
import { LanguageServerMessage } from "types"
import {
  LanguageClient,
  LanguageClientOptions,
  ServerOptions,
} from "vscode-languageclient/node"
import emitter from "utils/emitter"

async function createLanguageClient(args: {
  languageServerOptions: ServerOptions
}) {
  const languageClientOptions: LanguageClientOptions = {
    documentSelector: [{ scheme: "file" }],
  }
  const languageClient = new LanguageClient(
    "mentat-server",
    "mentat-server",
    args.languageServerOptions,
    languageClientOptions
  )

  languageClient.onNotification(
    "mentat/serverMessage",
    async (message: LanguageServerMessage) => {
      console.log("Emitting serverMessage")
      emitter.emit("mentat/serverMessage", message)
    }
  )
  languageClient.onNotification(
    "mentat/inputRequest",
    async (message: LanguageServerMessage) => {
      emitter.emit("mentat/inputRequest", message)
    }
  )

  await vscode.window.withProgress(
    { location: vscode.ProgressLocation.Notification },
    async (progress) => {
      progress.report({ message: "Mentat: Starting Language Client..." })
      await languageClient.start()
    }
  )

  return languageClient
}

async function startLanguageServer(context: vscode.ExtensionContext) {
  try {
    const languageServerOptions = await getLanguageServerOptions()
    const languageClient = await createLanguageClient({ languageServerOptions })

    const chatWebviewProvider = new WebviewProvider(
      context.extensionUri,
      languageClient
    )
    context.subscriptions.push(
      vscode.window.registerWebviewViewProvider(
        "MentatChat",
        chatWebviewProvider,
        {
          webviewOptions: { retainContextWhenHidden: true },
        }
      )
    )
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
  startLanguageServer(context)
}
