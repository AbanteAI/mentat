<script lang='ts'>
  import { WorkspaceFile } from "../../../types/globals";
  export let path: WorkspaceFile;
  export let index: number;
  export let toggleSelect: (i: number) => void;

  function handleToggleSelect() {
      toggleSelect(index)
  }
</script>

<div style="width: 100%; display: flex;">
  <input type="checkbox" checked={path.selected} on:change={handleToggleSelect} />
  <span style="flex: 1;">{path.name}</span>
</div>

