<script lang='ts'>
  import Fa from "svelte-fa";
  import { faCheck, faTimes, faSlash } from "@fortawesome/free-solid-svg-icons";

  import { FileInclusionStatus } from "../../../types/globals";

  export let status: FileInclusionStatus;
  export let renderMixedChildren: boolean = false;
  export let handleClick: () => void;
  const localHandleClick = () => {
    if (!_disabled) {
      handleClick();
    }
  }

  let _checked: boolean = false;
  let _crossed: boolean = false;
  let _faded: boolean = false;
  let _disabled: boolean = false;
  let _color: string | null = null;
  $: {
    _checked = false
    _crossed = false
    _faded = false
    _disabled = false
    _color = null
    if (renderMixedChildren) {
      _color = 'blue';
    } else {
      switch(status) {
        case FileInclusionStatus.notIncluded:
          break;
        case FileInclusionStatus.autoIncluded:
          _checked = true;
          _faded = true;
          break;
        case FileInclusionStatus.included:
          _checked = true;
          _color = 'green';
          break;
        case FileInclusionStatus.excluded:
          _crossed = true;
          _color = 'red';
          break;
        case FileInclusionStatus.autoExcluded:
          _crossed = true;
          _faded = true;
          _disabled = true;
          break;
      }
    }
  }
</script>

<!-- svelte-ignore a11y-click-events-have-key-events -->
<div 
    class="custom-checkbox {_color} { _faded ? 'faded' : '' } { _disabled ? 'disabled' : '' }" 
    on:click|stopPropagation={localHandleClick}
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
    margin: 0 0.6em;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    border: 1px solid var(--vscode-input-foreground);
  }
  .custom-checkbox.green {
    border: 1px solid green;
    color: green;
  }
  .custom-checkbox.red {
    border: 1px solid red;
    color: red;
  }
  .custom-checkbox.blue {
    border: 1px solid blue;
    color: blue;
  }
  .faded {
    border: 1px solid var(--vscode-input-placeholderForeground);
    color: var(--vscode-input-placeholderForeground);
  }
</style>