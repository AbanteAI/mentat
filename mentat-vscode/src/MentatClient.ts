import emitter from "emitter";
import { once } from "events";
import {
  LanguageServerMethod,
  LanguageServerNotification,
  LanguageServerRequest,
} from "types";
import * as vscode from "vscode";
import { LanguageClient, ServerOptions, State } from "vscode-languageclient/node";

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

    this.languageClient.onRequest(
      LanguageServerMethod.InputRequest,
      async (req: LanguageServerRequest) => {
        const languageClientResponsePromise = once(
          emitter,
          `mentat/inputRequest/${req.data.id}`
        );
        emitter.emit(LanguageServerMethod.InputRequest, req);
        const languageClientResponse = await languageClientResponsePromise;
        return languageClientResponse;
      }
    );

    this.languageClient.onNotification(
      LanguageServerMethod.SessionOutput,
      async (data: LanguageServerNotification) => {
        emitter.emit(LanguageServerMethod.SessionOutput, data);
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
}

export default MentatClient;
