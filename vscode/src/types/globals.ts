export enum Command {
    getWorkspaceFiles = 'getWorkspaceFiles',
    getResponse = 'getResponse',
    interrupt = 'interrupt',
    restart = 'restart',
}

export interface OutboundMessage {
    command: Command;
    data: any;
}

export enum Sender {
    user = 'user',
    assistant = 'assistant',
    system = 'system',
    files = 'files',
}

export interface InboundMessage {
    type: Sender;
    value: string | WorkspaceFile[];
}

export interface VsCodeApi {
    postMessage(message: OutboundMessage): void;
}

export interface WorkspaceFile {
    name: string;
    uri: string;
    url: string;
    selected?: boolean;
}
