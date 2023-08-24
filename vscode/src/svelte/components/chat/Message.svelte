<script lang="ts">
  import { Sender } from "../../../types/globals";
  export let type: Sender;
  export let value: string;

  // TODO: Identify/render code blocks
  // $: {
  //   handleUpdateValue(value);
  // }
  // const handleUpdateValue = (value: string) => {}
</script>

<div class={`message ${type}`}>
  {value}
</div>

<style>
  .message {
    padding: 0.5em;
    margin: 0.5em;
    border-radius: 0.5em;
    max-width: 80%;
    overflow-wrap: break-word;
  }
  
  .message.user {
    background-color: var(--vscode-button-background);
    margin-left: 3em;
    align-self: flex-end;
  }
  
  .message.assistant {
    background-color: #7646b3ff;  /* A darker shade of the GPT4 color */
    margin-right: 3em;
    align-self: flex-start;
  }
  
  .message.system {
    background-color: gray;
    margin-right: 3em;
    align-self: flex-start;
  }
</style>