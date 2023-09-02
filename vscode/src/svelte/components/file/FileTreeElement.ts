import { writable } from 'svelte/store';
import { WorkspaceGraphElement, FileInclusionStatus, MentatArgs } from '../../../types/globals';

export class FileTreeElement {
    private _children: FileTreeElement[] | undefined;
    // A svelte-subscribable store that stores broadcasts changes in status
    public statusStore = writable(FileInclusionStatus.notIncluded);
    public status: FileInclusionStatus | undefined; // A locally-accessible cache of status

    constructor(
        public file: WorkspaceGraphElement, // File metadata
    ) {
        this.statusStore.subscribe((s) => (this.status = s));
    }

    get children(): FileTreeElement[] | undefined {
      if (!this._children && this.file.children) {
          this._children = this.file.children.map((child) => {
              return new FileTreeElement(child);
          });
      }
      return this._children;
    }

    handleClick() {
        // Determine and propagate changes to file selection status
        switch (this.status) {
            case FileInclusionStatus.notIncluded:
                this.setStatus(FileInclusionStatus.included, FileInclusionStatus.autoIncluded);
                break;
            case FileInclusionStatus.included:
                this.setStatus(FileInclusionStatus.notIncluded, FileInclusionStatus.notIncluded);
                break;
            case FileInclusionStatus.autoIncluded:
                this.setStatus(FileInclusionStatus.excluded, FileInclusionStatus.autoExcluded);
                break;
            case FileInclusionStatus.excluded:
                this.setStatus(FileInclusionStatus.autoIncluded, FileInclusionStatus.autoIncluded);
                break;
            case FileInclusionStatus.autoExcluded:
                throw new Error('Auto-excluded files should not be clickable');
        }
    }

    setStatus(status: FileInclusionStatus, setChildrenTo: FileInclusionStatus | null = null) {
        this.statusStore.set(status);
        if (setChildrenTo !== null && this.children) {
            this.children?.forEach((child) => {
                child.setStatus(setChildrenTo, setChildrenTo);
            });
        }
    }

    getMentatArgs(args?: MentatArgs): MentatArgs {
        args = args || { paths: [], exclude_paths: [] };
        switch (this.status) {
            case FileInclusionStatus.included:
                args.paths.push(this.file.path);
                break;
            case FileInclusionStatus.excluded:
                args.exclude_paths.push(this.file.path);
                break;
        }
        if (this.children) {
            this.children.forEach((child) => {
                args = child.getMentatArgs(args);
            });
        }
        return args;
    }

    get hasMixedChildren(): boolean {
        if (this.children) {
            const firstChildStatus = this.children[0].status;
            return this.children.some((child) => child.status !== firstChildStatus);
        }
        return false;
    }
}
