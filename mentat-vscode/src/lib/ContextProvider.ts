import path from "path";
import {
    Event,
    EventEmitter,
    ProviderResult,
    TreeDataProvider,
    TreeItem,
    TreeItemCollapsibleState,
} from "vscode";
import fs from "fs";

// TODO: Add full on file explorer with checkboxes to add and remove from context;
// this will take a decent chunk of work to make efficient and update when files are added or removed
export class ContextProvider implements TreeDataProvider<ContextFile> {
    constructor(private workspaceRoot: string) {}

    private _onDidChangeTreeData: EventEmitter<
        ContextFile | undefined | null | void
    > = new EventEmitter<ContextFile | undefined | null | void>();
    readonly onDidChangeTreeData: Event<ContextFile | undefined | null | void> =
        this._onDidChangeTreeData.event;

    private fileTree: { [key: string]: any } = {};

    private createFileTree(features: string[]) {
        for (const feature of features) {
            const relPath = path.relative(this.workspaceRoot, feature);
            var curTree: { [key: string]: any } = this.fileTree;
            for (const segment of relPath.split(path.sep)) {
                if (!(segment in curTree)) {
                    curTree[segment] = {};
                }
                curTree = curTree[segment];
            }
        }
    }

    updateContext(features: string[], autoFeatures: string[]) {
        this.createFileTree([...features, ...autoFeatures]);
        this._onDidChangeTreeData.fire();
    }

    getTreeItem(element: ContextFile): TreeItem | Thenable<TreeItem> {
        return element;
    }

    getChildren(
        element?: ContextFile | undefined
    ): ProviderResult<ContextFile[]> {
        if (!element) {
            return [new ContextFile(this.workspaceRoot, this.workspaceRoot)];
        } else if (!element.isDir) {
            return [];
        } else {
            return fs
                .readdirSync(element.absPath)
                .map(
                    (filename) => new ContextFile(filename, this.workspaceRoot)
                );
        }
    }
}

class ContextFile extends TreeItem {
    isDir: boolean;

    constructor(public absPath: string, workspaceRoot: string) {
        const isDir = fs.lstatSync(absPath).isDirectory();
        super(
            path.basename(absPath),
            isDir
                ? TreeItemCollapsibleState.Expanded
                : TreeItemCollapsibleState.None
        );
        this.isDir = isDir;
        this.tooltip = path.relative(workspaceRoot, absPath);
    }

    iconPath = {
        light: "",
        dark: "",
    };
}
