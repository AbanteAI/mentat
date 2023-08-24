<script lang='ts'>
  import { WorkspaceFile } from "../../../types/globals";
  export let file: WorkspaceFile;
  export let index: number;
  export let toggleSelect: (i: number) => void;

  function handleToggleSelect() {
      toggleSelect(index)
  }
</script>

<div>
  <input 
    type="checkbox" 
    checked={file.selected} 
    on:change={handleToggleSelect} 
  />
  <span style="flex: 1;">{file.name}</span>
</div>

<style>
  div {
    width: 100%;
    display: flex;
    align-items: center;
    padding: 0.5rem;
  }
  input {
    scale: 1.5;
  }
</style>
