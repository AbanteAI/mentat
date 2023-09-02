<script lang='ts'>
  import Fa from "svelte-fa";
  import { faCaretRight } from "@fortawesome/free-solid-svg-icons";

  import { FileInclusionStatus } from "../../../types/globals";
  import { FileTreeElement } from "./FileTreeElement";
  import File from './File.svelte';
  import Checkbox from "./Checkbox.svelte";
  
  export let file: FileTreeElement;
  export let indent: number = 0;
  let status: FileInclusionStatus;
  file.statusStore.subscribe(value => status = value);

  let isOpen: boolean = indent === 0;
  const handleClickRow = () => {
    if (file.file.children) {
      isOpen = !isOpen;
    } else {
      file.handleClick();
    }
  }
  const handleClickCheckbox = () => {
    file.handleClick();
  }
  
  let _faded: boolean = false;
  $: _faded = status === FileInclusionStatus.autoIncluded || status === FileInclusionStatus.autoExcluded;

  // Special case where checkbox renders differently
  let renderMixedChildren: boolean = false;
  $: renderMixedChildren = !isOpen && file.hasMixedChildren && !!status;
    
</script>

<div class="file-group">
  <!-- svelte-ignore a11y-click-events-have-key-events -->
  <div 
    class="file-line {_faded ? 'faded' : ''}" 
    on:click={handleClickRow}
    role="button"
    tabindex="0"
  >
    <div style={`width: ${indent}em`} />
    {#if file.children}
      <span class="caret {isOpen ? 'open' : ''}" >
        <Fa icon={faCaretRight} />
      </span>
    {:else}
      <span style="width: 0.5em" />
    {/if}
    <Checkbox 
      status={status} 
      renderMixedChildren={renderMixedChildren}
      handleClick={handleClickCheckbox} 
    />
    <span class="file-name">{file.file.name}</span>
  </div>
  
  <div class="children-container {isOpen ? 'open' : ''}">
    {#if isOpen && file.children}
      {#each file.children as child}
        <File 
          file={child} 
          indent={indent + 1} 
        />
      {/each}
    {/if}
  </div>
</div>

<style>
  .file-group {
    display: flex;
    flex-direction: column;
  }
  .file-line {
    display: flex;
    align-items: center;
    padding: 0.2rem;
    color: var(--vscode-input-foreground);
  }
  .file-line:hover {
    background-color: var(--vscode-input-background);
    cursor: pointer;
  }
  .file-line.faded {
    color: var(--vscode-input-placeholderForeground);
  }
  .children-container {
    overflow: hidden;
    transition: max-height 0.3s ease-in-out;
    max-height: 0;
  }
  .children-container.open {
    max-height: 100%;
  }
  .caret {
    width: 0.5em;
    transition: transform 0.3s ease;
  }
  .caret.open {
    transform: rotate(90deg); /* rotate arrow when open */
  }
</style>
