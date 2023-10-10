import { useState } from "react";

function Chat() {
  const [messages, setMessages] = useState("");

  setMessages("This is a fake message: meow");

  console.log(messages);

  return (
    <div>
      <title>This is the chat interface</title>
      <p>meow</p>
      <p>meow</p>
      <p>meow</p>
    </div>
  );
}

export { Chat };
