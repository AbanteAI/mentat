<script lang="ts">
  import { onMount, onDestroy } from "svelte";
  import File from './File.svelte'
  import { VsCodeApi, Command, WorkspaceFile, Sender } from "../../../types/globals";

  export let vscode: VsCodeApi;
  export let startMentat: (include: Iterable<string>) => void;

  // Setup and maintain the list of files
  let files: WorkspaceFile[] = []
  const refreshFiles = () => {
    vscode.postMessage({ command: Command.getWorkspaceFiles, data: null });
  }
  const handleReceiveFiles = (event: MessageEvent) => {
    const { type, value } = event.data
    if (type === Sender.files) {
      files = value.map((file: WorkspaceFile) => ({ ...file, selected: false }))
    }
  }
  onMount(() => {
    window.addEventListener('message', handleReceiveFiles);    
    refreshFiles()
  })
  onDestroy(() => window.removeEventListener('message', handleReceiveFiles));

  // Callback to select a path
  const toggleSelect = (i: number) => {
    files[i].selected = !files[i].selected
  }

  // Start Mentat
  const handleStartMentat = () => {
    startMentat(files.filter(file => file.selected).map(file => file.name))
  }
  
</script>

<h1>Paths</h1>
<button on:click={refreshFiles}>Refresh</button>
{#if files}
    {#each files as file, index (file.uri)}
      <File file={file} index={index} toggleSelect={toggleSelect} />
    {/each}
{/if}
<button on:click={handleStartMentat}>Start Mentat</button>