<script lang="ts">
  import { onMount, onDestroy } from "svelte";
  import Fa from 'svelte-fa'
  import { faArrowsRotate } from '@fortawesome/free-solid-svg-icons'

  import { VsCodeApi, Command, Sender, WorkspaceGraphElement, MentatArgs } from "../../../types/globals";
  import { FileTreeElement } from "./FileTreeElement";
  import File from './File.svelte'

  export let vscode: VsCodeApi;
  export let startMentat: (args: MentatArgs) => void;

  
  // Get the file root on mount, or when the refresh button is clicked
  let root: FileTreeElement | null = null;
  const refreshFiles = () => {
    root = null;
    vscode.postMessage({ command: Command.getWorkspaceGraph, data: null });
  }
  const handleReceiveFiles = (event: MessageEvent) => {
    const { type, value } = event.data
    if (type === Sender.files && value) {
      root = new FileTreeElement(value as WorkspaceGraphElement)
    }
  }
  onMount(() => {
    window.addEventListener('message', handleReceiveFiles);    
    refreshFiles()
  })
  onDestroy(() => window.removeEventListener('message', handleReceiveFiles));

  
  // Start Mentat
  const handleStartMentat = () => {
    if (!root) return;
    const args = root.getMentatArgs();
    startMentat(args)
  }
  
</script>

<div class="header">
  <p>Select Files</p>
  <button on:click={refreshFiles}><Fa icon={faArrowsRotate} /></button>
</div>
<div class="file-container">
  {#if root}
    <File file={root} />
  {/if}
</div>
<button on:click={handleStartMentat}>Start Mentat</button>

<style>
  .header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.5em;
  }
  .file-container {
    overflow: auto;
  }
</style>