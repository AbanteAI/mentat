import { useState } from "react";

function Chat() {
  const [messages, setMessages] = useState("");

  console.log("hey");

  return (
    <div>
      <h1>This is a title</h1>
      <h2>This is another title</h2>
      <p>Hello</p>
      <p>Hello</p>
      <p>Hello</p>
      <p>Hello</p>
    </div>
  );
}

export { Chat };
