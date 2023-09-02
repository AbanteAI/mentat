<script lang="ts">
  import { ChatView, FileView } from './components';
  import { VsCodeApi, Command, MentatArgs } from '../types/globals';

  export let vscode: VsCodeApi;
  
  let isRunning: boolean = false;
  const startMentat = (args: MentatArgs): void => {
    vscode.postMessage({ command: Command.restart, data: args })
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
    <FileView vscode={vscode} startMentat={startMentat} />
  {/if}
</div>

<style>
  .app {
    display: flex;
    flex-direction: column;
    height: 100vh;
    background-color: var(--vscode-sideBar-background);
  }
</style>
