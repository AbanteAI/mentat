// This class replaces `acquireVsCodeApi()` for testing or when running in a browser.

import { VsCodeApi, Command, OutboundMessage, Sender, InboundMessage, WorkspaceFile } from '../types/globals';

export default class MockVSCode implements VsCodeApi {
    _streaming = false;
    _interrupt = false;
    _chunkLength = 2;

    postMessage(message: OutboundMessage) {
        // Send a message OUT to vscode.extension
        console.log('Message OUT', message);
        switch (message.command) {
            case Command.getWorkspaceFiles:
                const testFiles = ['main.ts', 'main.css', 'index.html'].map((name) => ({
                    name,
                    uri: `file:///src/${name}`,
                    url: `http://localhost:3000/${name}`,
                }));
                this.respond({ type: Sender.files, value: testFiles });
                break;
            case Command.getResponse:
                this.respond({ type: Sender.user, value: message.data });
                this.stream(`Responding to ${message.data}`);
                break;
            case Command.interrupt:
                if (this._streaming) {
                    this._interrupt = true;
                }
                break;
            default:
                message;
                break;
        }
    }

    respond(message: InboundMessage): void {
        // Send a message IN to the browser
        console.log('Message IN', message);
        window.postMessage(message);
    }

    async stream(value: string) {
        // Stream a message to the browser
        this._streaming = true;
        const endStream = () => {
            this._interrupt = false;
            this._streaming = false;
            this.respond({ type: Sender.assistant, value: '@@endstream' });
        };
        this.respond({ type: Sender.assistant, value: '@@startstream' });
        let remaining = value;
        while (true) {
            if (this._interrupt) {
                endStream();
                break;
            }
            const chunk = remaining.slice(0, this._chunkLength);
            remaining = remaining.slice(this._chunkLength);
            this.respond({ type: Sender.assistant, value: chunk });
            if (!remaining) {
                endStream();
                break;
            }
            // Sleep 100 ms
            await new Promise((resolve) => setTimeout(resolve, 100));
        }
    }
}
