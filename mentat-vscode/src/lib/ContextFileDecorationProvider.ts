import {
    CancellationToken,
    EventEmitter,
    Event,
    FileDecoration,
    FileDecorationProvider,
    ProviderResult,
    Uri,
    ThemeColor,
} from "vscode";

// Currently not registered in extension.ts!
export class ContextFileDecorationProvider implements FileDecorationProvider {
    constructor() {}

    private _onDidChangeFileDecoration: EventEmitter<Uri | Uri[] | undefined> =
        new EventEmitter<Uri | Uri[] | undefined>();
    readonly onDidChangeFileDecorations: Event<Uri | Uri[] | undefined> =
        this._onDidChangeFileDecoration.event;

    private included_resources: Set<string> = new Set();

    refresh(included_resources: string[]) {
        const changed_resources = [
            ...included_resources,
            ...this.included_resources,
        ].map((resource: string) => Uri.file(resource));
        this.included_resources = new Set(included_resources);
        this._onDidChangeFileDecoration.fire(changed_resources);
    }

    provideFileDecoration(
        uri: Uri,
        token: CancellationToken
    ): ProviderResult<FileDecoration> {
        if (this.included_resources.has(uri.fsPath)) {
            return {
                badge: "C",
                color: new ThemeColor("mentat.fileInContext"),
                propagate: false,
            };
        }
        return;
    }
}
