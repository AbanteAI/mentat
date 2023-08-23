<script lang="ts">
  import { onMount, onDestroy } from "svelte";
  import Path from './Path.svelte'
  import { VsCodeApi, Command, WorkspaceFile } from "../../../types/globals";

  export let vscode: VsCodeApi;
  export let startMentat: (paths: Iterable<string>) => void;

  // Setup and maintain the list of paths
  let paths: WorkspaceFile[] = []
  const refreshPaths = () => {
    vscode.postMessage({ command: Command.getPaths, data: null });
  }
  const handleReceivePaths = (event: MessageEvent) => {
    const { type, value } = event.data
    if (type === 'paths') {
      paths = value.map((path: string) => ({ name: path, selected: false }))
    }
  }
  onMount(() => {
    window.addEventListener('message', handleReceivePaths);    
    refreshPaths()
  })
  onDestroy(() => window.removeEventListener('message', handleReceivePaths));

  // Callback to select a path
  const toggleSelect = (i: number) => {
    paths[i].selected = !paths[i].selected
  }

  // Start Mentat
  const handleStartMentat = () => {
    startMentat(paths.filter(path => path.selected).map(path => path.name))
  }
  
</script>

<h1>Paths</h1>
<button on:click={refreshPaths}>Refresh</button>
{#if paths}
  <ul>
    {#each paths as path, index (path.name)}
      <Path path={path} index={index} toggleSelect={toggleSelect} />
    {/each}
  </ul>
{/if}
<button on:click={handleStartMentat}>Start Mentat</button>