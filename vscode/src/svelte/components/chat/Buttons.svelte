<script lang="ts">
  export let handleGetResponse: () => void;
  export let handleInterrupt: () => void;
  export let handleRestart: () => void;
</script>

<div class="button-container">
  <button class="button" on:click={handleGetResponse}>Get Response</button>
  <button class="button" on:click={handleInterrupt}>Interrupt</button>
  <button class="button" on:click={handleRestart}>Restart</button>
</div>

<style>
  .button-container {
    display: flex;
    flex-direction: row;
    justify-content: center;
  }
  
  .button {
    color: var(--vscode-button-foreground);
    background-color: var(--vscode-button-background);
    padding: 0.5em;
    margin: 0.5em;
    border: 0;
  }
  
  .button:hover {
    background-color: var(--vscode-button-hoverBackground);
  }
</style>
