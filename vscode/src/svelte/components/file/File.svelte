<script lang='ts'>
  import { WorkspaceFile } from "../../../types/globals";
  export let file: WorkspaceFile;
  export let index: number;
  export let toggleSelect: (i: number) => void;

  function handleToggleSelect() {
      toggleSelect(index)
  }
</script>

<div style="width: 100%; display: flex;">
  <input type="checkbox" checked={file.selected} on:change={handleToggleSelect} />
  <span style="flex: 1;">{file.name}</span>
</div>

