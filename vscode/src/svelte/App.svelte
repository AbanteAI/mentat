<script lang="ts">
  import { ChatView, PathView } from './components';
  import { VsCodeApi, Command } from '../types/globals';

  export let vscode: VsCodeApi;
  
  let isRunning: boolean = false;
  const startMentat = (paths: Iterable<string>): void => {
    vscode.postMessage({ command: Command.restart, data: paths })
    isRunning = true;
  }
  const restartMentat = (): void => {
    isRunning = false;
    // vscode.postMessage({ command: 'restart' });
  }
</script>

<div class="app">
  {#if isRunning}
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
