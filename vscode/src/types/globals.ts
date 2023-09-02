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
    // Based on file/parent checked:   file  prt1  prt2
    notIncluded = 'notIncluded',   //  -     -     -
    included = 'included',         //  X     -     -
    excluded = 'excluded',         //  X     X     -
    autoIncluded = 'autoIncluded', //  -     X     -
    autoExcluded = 'autoExcluded', //  -     X     X
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
