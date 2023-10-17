import * as vscode from "vscode";
import { LanguageClient, ServerOptions, State } from "vscode-languageclient/node";

import { ChatMessage } from "./types";

class MentatClient {
  context: vscode.ExtensionContext;
  languageServerOptions: ServerOptions;
  languageServerClient?: LanguageClient;
  private restartCount: number;

  constructor(context: vscode.ExtensionContext, serverOptions: ServerOptions) {
    this.context = context;
    this.languageServerOptions = serverOptions;
    this.restartCount = 0;
  }

  async startLanguageClient() {
    this.languageServerClient = new LanguageClient(
      "mentat-server",
      "mentat-server",
      this.languageServerOptions,
      {
        documentSelector: [{ language: "*" }],
      }
    );

    this.languageServerClient.onDidChangeState(async (e) => {
      console.log(`language client state changed: ${e.oldState} ▸ ${e.newState} `);
      if (e.newState === State.Stopped) {
        console.log("language client stopped, restarting...");
        await this.languageServerClient?.dispose();
        console.log("language client disposed");
        vscode.window.withProgress(
          { location: vscode.ProgressLocation.Notification },
          async (progress) => {
            progress.report({ message: "Mentat: restarting client" });
            await this.startLanguageClient();
          }
        );
      }
      if (e.newState === State.Starting) {
        this.restartCount = this.restartCount + 1;
        console.log(`this.restartCount=${this.restartCount}`);
      }
    });

    console.log("language server options", this.languageServerOptions);
    await vscode.window.withProgress(
      { location: vscode.ProgressLocation.Notification },
      async (progress) => {
        progress.report({ message: "Mentat: Launching server..." });
        await this.languageServerClient?.start();
      }
    );
  }

  async sendChatMessage(chatMessage: ChatMessage) {
    const result = await this.languageServerClient?.sendRequest(
      "mentat/chatMessage",
      chatMessage
    );
  }
}

export { MentatClient };
