export enum Command {
    getWorkspaceGraph = 'getWorkspaceGraph',
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
    value: string | WorkspaceGraphElement;
}

export interface VsCodeApi {
    postMessage(message: OutboundMessage): void;
}

export enum FileInclusionStatus {
    notIncluded,  // Not included, parent not included.
    autoIncluded, // Not included, parent included
    included,     // Included, parent not included
    autoExcluded, // n/a, parent excluded
    excluded,     // Excluded, parent included
}

export interface WorkspaceGraphElement {
    name: string;
    uri: string;
    path: string;
    children?: WorkspaceGraphElement[];
}

export interface MentatArgs {
    paths: string[];
    // eslint-disable-next-line @typescript-eslint/naming-convention
    exclude_paths: string[];  // match Mentat/Python style
}
