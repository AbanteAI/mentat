<script>
  import { onMount, onDestroy } from "svelte";
  import Path from './Path.svelte'

  export let vscode = ''
  export let startMentat = () => {}

  // Setup and maintain the list of paths
  let paths
  const refreshPaths = () => {
    vscode.postMessage({ command: 'getPaths' });
  }
  const handleReceivePaths = (event) => {
    const { type, value } = event.data
    if (type === 'paths') {
      paths = value.map(path => ({ name: path, selected: false }))
    }
  }
  onMount(() => {
    window.addEventListener('message', handleReceivePaths);    
    refreshPaths()
  })
  onDestroy(() => window.removeEventListener('message', handleReceivePaths));

  // Callback to select a path
  const toggleSelect = (i) => {
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