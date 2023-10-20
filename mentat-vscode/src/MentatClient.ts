import emitter from "emitter";
import { once } from "events";
import {
  LanguageClientMessage,
  LanguageServerMethod,
  LanguageServerNotification,
  LanguageServerRequest,
} from "types";
import * as vscode from "vscode";
import { LanguageClient, ServerOptions, State } from "vscode-languageclient/node";

class MentatClient {
  context: vscode.ExtensionContext;
  languageServerOptions: ServerOptions;
  private languageClient?: LanguageClient;
  private restartCount: number;

  constructor(context: vscode.ExtensionContext, serverOptions: ServerOptions) {
    this.context = context;
    this.languageServerOptions = serverOptions;
    this.restartCount = 0;
  }

  // Handler methods that the WebViews call

  handleCreateSession() {
    this.languageClient!.sendNotification(LanguageServerMethod.CreateSession);
  }

  handleGetInput(message: LanguageClientMessage) {
    emitter.emit(
      `${LanguageServerMethod.GetInput}/${message.data.inputRequestId}`,
      message
    );
  }

  // Lifecylce methods

  async startLanguageClient() {
    this.languageClient = new LanguageClient(
      "mentat-server",
      "mentat-server",
      this.languageServerOptions,
      {
        documentSelector: [{ language: "*" }],
      }
    );

    // Handle requests/notifications from the Webview
    // TODO: register emitter listeners here

    // Handle requests/notifications from the Language Server
    this.languageClient.onRequest(
      LanguageServerMethod.GetInput,
      async (req: LanguageServerRequest) => {
        const languageClientResponsePromise = once(
          emitter,
          `${LanguageServerMethod.GetInput}/${req.id}`
        );
        emitter.emit(LanguageServerMethod.GetInput, req);
        const languageClientResponse = await languageClientResponsePromise;
        return languageClientResponse;
      }
    );

    this.languageClient.onNotification(
      LanguageServerMethod.StreamSession,
      async (data: LanguageServerNotification) => {
        emitter.emit(LanguageServerMethod.StreamSession, data);
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
    await vscode.window.withProgress(
      { location: vscode.ProgressLocation.Notification },
      async (progress) => {
        progress.report({ message: "Mentat: Launching server..." });
        await this.languageClient?.start();
      }
    );
  }
}

export default MentatClient;
