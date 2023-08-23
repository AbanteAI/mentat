<script>
  import { ChatView, PathView } from './components';
  export let vscode;
  
  let _running = false;
  const startMentat = (paths) => {
    vscode.postMessage({ command: 'restart', data: paths })
    _running = true;
  }
  const restartMentat = () => {
    _running = false;
    // vscode.postMessage({ command: 'restart' });
  }
</script>

<div class="app">
  {#if _running}
    <ChatView vscode={vscode} restartMentat={restartMentat} />
  {:else}
    <PathView vscode={vscode} startMentat={startMentat} />
  {/if}
</div>

<style>
  .app {
    display: flex;
    flex-direction: column;
    height: 100vh;
  }
</style>
