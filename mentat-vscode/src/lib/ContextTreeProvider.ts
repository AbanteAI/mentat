import path from "path";
import {
    Event,
    EventEmitter,
    ProviderResult,
    TreeDataProvider,
    TreeItem,
    TreeItemCollapsibleState,
    Uri,
} from "vscode";
import fs from "fs";

// TODO: Add full on file explorer with checkboxes to add and remove from context;
// this will take a decent chunk of work to make efficient and update when files are added or removed
export class ContextTreeProvider implements TreeDataProvider<ContextFile> {
    constructor(private workspaceRoot: string) {}

    private _onDidChangeTreeData: EventEmitter<
        ContextFile | undefined | null | void
    > = new EventEmitter<ContextFile | undefined | null | void>();
    readonly onDidChangeTreeData: Event<ContextFile | undefined | null | void> =
        this._onDidChangeTreeData.event;

    private fileTree: { [key: string]: any } = {};

    // TODO: This will stall on symlink loops
    private async createFileTree(features: string[]) {
        this.fileTree = {};
        for (const feature of features) {
            var curTree: { [key: string]: any } = this.fileTree;
            for (const segment of feature.split(path.sep)) {
                if (!(segment in curTree)) {
                    curTree[segment] = {};
                }
                curTree = curTree[segment];
            }
        }
    }

    async updateContext(features: string[]) {
        await this.createFileTree(features);
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
        } else {
            var curTree = this.fileTree;
            for (const segment of element.absPath.split(path.sep)) {
                if (!(segment in curTree)) {
                    break;
                }
                curTree = curTree[segment];
            }
            return Object.keys(curTree).map(
                (filename) =>
                    new ContextFile(
                        path.join(element.absPath, filename),
                        this.workspaceRoot
                    )
            );
        }
    }
}

class ContextFile extends TreeItem {
    constructor(public absPath: string, workspaceRoot: string) {
        const isDir = fs.lstatSync(absPath).isDirectory();
        super(
            path.basename(absPath),
            isDir
                ? TreeItemCollapsibleState.Expanded
                : TreeItemCollapsibleState.None
        );
        this.resourceUri = Uri.file(absPath);
        this.iconPath = undefined;
    }
}
