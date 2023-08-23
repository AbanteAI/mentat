export enum Command {
    getPaths = 'getPaths',
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
    paths = 'paths',
}

export interface InboundMessage {
    type: Sender;
    value: any;
}

export interface VsCodeApi {
    postMessage(message: OutboundMessage): void;
}

export interface WorkspaceFile {
    name: string;
    selected: boolean;
}
