<script lang='ts'>
  import Fa from "svelte-fa";
  import { faCheck, faTimes, faSlash } from "@fortawesome/free-solid-svg-icons";

  import { FileInclusionStatus } from "../../../types/globals";

  export let status: FileInclusionStatus;
  export let renderMixedChildren: boolean = false;
  export let handleClick: () => void;

  let _checked: boolean = false;
  let _crossed: boolean = false;
  let _faded: boolean = false;
  $: {
    _checked = false
    _crossed = false
    _faded = false
    if (!renderMixedChildren) {
      switch(status) {
        case FileInclusionStatus.notIncluded:
          break;
        case FileInclusionStatus.autoIncluded:
          _checked = true;
          _faded = true;
          break;
        case FileInclusionStatus.included:
          _checked = true;
          break;
        case FileInclusionStatus.excluded:
          _crossed = true;
          break;
        case FileInclusionStatus.autoExcluded:
          _crossed = true;
          _faded = true;
          break;
      }
    }
  }
</script>

<!-- svelte-ignore a11y-click-events-have-key-events -->
<div 
    class="custom-checkbox { _faded ? 'faded' : '' }" 
    on:click|stopPropagation={handleClick}
    role="checkbox"
    aria-checked={_checked ? "true" : "false"}
    tabindex="0"
>
  {#if renderMixedChildren}
    <Fa icon={faSlash} />
  {:else if _checked}
    <Fa icon={faCheck} />
  {:else if _crossed}
    <Fa icon={faTimes} />
  {/if}
</div>

<style>
  .custom-checkbox {
    display: inline-flex;
    width: 1em;
    height: 1em;
    margin: 0 0.25em;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    border: 2px solid var(--vscode-input-foreground);
  }
  .faded {
    border: 2px solid var(--vscode-input-placeholderForeground);
    color: var(--vscode-input-placeholderForeground);
  }
</style>