import {
    CancellationToken,
    Event,
    FileDecoration,
    FileDecorationProvider,
    ProviderResult,
    Uri,
} from "vscode";

// TODO: add some sort of badge or color to files that are included
// Currently not registered in extension.ts!
class ContextFileDecorationProvider implements FileDecorationProvider {
    constructor() {}

    onDidChangeFileDecorations?: Event<Uri | Uri[] | undefined> | undefined;

    provideFileDecoration(
        uri: Uri,
        token: CancellationToken
    ): ProviderResult<FileDecoration> {
        throw new Error("Method not implemented.");
    }
}
