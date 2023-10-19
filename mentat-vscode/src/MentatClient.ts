import emitter from "emitter";
import { once } from "events";
import * as vscode from "vscode";
import { LanguageClient, ServerOptions, State } from "vscode-languageclient/node";

import { MentatSessionStreamMessage } from "./types";
import { ChatMessage } from "./types";

class MentatClient {
  context: vscode.ExtensionContext;
  languageServerOptions: ServerOptions;
  languageClient?: LanguageClient;
  private restartCount: number;

  constructor(context: vscode.ExtensionContext, serverOptions: ServerOptions) {
    this.context = context;
    this.languageServerOptions = serverOptions;
    this.restartCount = 0;
  }

  async startLanguageClient() {
    this.languageClient = new LanguageClient(
      "mentat-server",
      "mentat-server",
      this.languageServerOptions,
      {
        documentSelector: [{ language: "*" }],
      }
    );

    // Handle notifications from the Language Server
    // this.languageClient.onNotification("mentat/inputRequest", async (params: any) => {
    //   console.log(`Got params ${params} from Language Server`);
    //   emitter.emit("mentat/inputRequest", params);
    // });

    this.languageClient.onRequest(
      "input_request",
      async (message: MentatSessionStreamMessage) => {
        console.log(`Got params ${message} from Language Server`);

        const webviewResponsePromise = once(emitter, `input_request:${message.id}`);
        emitter.emit("input_request", message);
        const webviewResponse = await webviewResponsePromise;

        return webviewResponse;
      }
    );

    this.languageClient.onNotification(
      "default",
      async (message: MentatSessionStreamMessage) => {
        emitter.emit("default", message);
      }
    );

    // Restart the LanguageClient if it's stopped
    this.languageClient.onDidChangeState(async (e) => {
      console.log(`language client state changed: ${e.oldState} ▸ ${e.newState} `);
      if (e.newState === State.Stopped) {
        console.log("language client stopped, restarting...");
        await this.languageClient?.dispose();
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

    // Start the LanguageClient
    console.log("language server options", this.languageServerOptions);
    await vscode.window.withProgress(
      { location: vscode.ProgressLocation.Notification },
      async (progress) => {
        progress.report({ message: "Mentat: Launching server..." });
        await this.languageClient?.start();
      }
    );
  }

  async createSession() {
    const response = await this.languageClient?.sendRequest("mentat/createSession", {
      test: "test",
    });

    console.log(`Got response: ${response}`);
  }

  async sendChatMessage(chatMessage: ChatMessage) {
    const result = await this.languageClient?.sendRequest(
      "mentat/chatMessage",
      chatMessage
    );
  }
}

export default MentatClient;
