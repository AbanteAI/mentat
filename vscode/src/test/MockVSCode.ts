// This class replaces `acquireVsCodeApi()` for testing or when running in a browser.

import { VsCodeApi, Command, OutboundMessage, Sender, InboundMessage, WorkspaceGraphElement } from '../types/globals';

let fileId: number = 0;
const mockFile = (prefix: string = ''): WorkspaceGraphElement => ({
    name: `file${prefix + fileId++}`,
    uri: `file:///src/file${prefix + fileId}`,
    path: `/src/file${prefix + fileId}`,
});
const mockFiles = (): WorkspaceGraphElement => {
    const root = mockFile();
    root.children = [];
    ['src', 'dist', 'node_modules'].forEach((name) => {
        const child = mockFile(name);
        child.children = [];
        for (let i = 0; i < 20; i++) {
            child.children?.push(mockFile(name));
        }
        root.children?.push(child);
    });
    return root;
};

export default class MockVSCode implements VsCodeApi {
    _streaming = false;
    _interrupt = false;
    _chunkLength = 2;

    postMessage(message: OutboundMessage) {
        // Send a message OUT to vscode.extension
        console.log('Message OUT', message);
        switch (message.command) {
            case Command.getWorkspaceGraph:
                const testWorkspaceGraph: WorkspaceGraphElement = mockFiles();
                this.respond({ type: Sender.files, value: testWorkspaceGraph });
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
