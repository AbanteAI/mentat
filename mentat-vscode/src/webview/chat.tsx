import { useState } from "react";

function Chat() {
  const [messages, setMessages] = useState("");

  setMessages("This is a fake message");

  console.log(messages);

  return (
    <div>
      <p>Hello</p>
      <p>Hello</p>
      <p>Hello</p>
      <p>Hello</p>
    </div>
  );
}

export { Chat };
