<script>
  export let type = "";
  export let value = "";

  $: {
    handleUpdateValue(value);
  }
  const handleUpdateValue = (value) => {
    // TODO: Identify/render code blocks
  }
</script>

<div class={`message ${type}`}>
  {value}
</div>

<style>
  .message {
    color: #fff;
    padding: 0.5em;
    margin: 0.5em;
    border-radius: 0.5em;
  }
  
  .message.user {
    background-color: blue;
    margin-left: 3em;
    align-self: flex-end;
  }
  
  .message.assistant {
    background-color: purple;
    margin-right: 3em;
    align-self: flex-start;
  }
  
  .message.system {
    background-color: gray;
    margin-right: 3em;
    align-self: flex-start;
  }
</style>