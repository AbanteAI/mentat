import { useEffect, useState } from "react";

import { ChatMessage } from "../../types";
import { ChatHistory } from "./ChatHistory";
import { ChatInput } from "./ChatInput";

const fakeMessages: ChatMessage[] = [
  {
    id: "0",
    orderId: 0,
    content: "I'm using Mentat",
    createdBy: "client",
  },
  {
    id: "1",
    orderId: 1,
    content: "Whoa this is another chat message!",
    createdBy: "client",
  },
];

function Chat() {
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>(fakeMessages);

  function handleMessage(payload: any) {
    console.log(`Webview got message from Extension: ${payload}`);
  }

  useEffect(() => {
    document.addEventListener("message", handleMessage);
    return () => {
      document.removeEventListener("message", handleMessage);
    };
  }, []);

  return (
    <div className="border border-red-500 h-screen">
      <div className="flex flex-col border border-green-500 p-1 h-full">
        <ChatHistory chatMessages={chatMessages} />
        <ChatInput chatMessages={chatMessages} setChatMessages={setChatMessages} />
      </div>
    </div>
  );
}

export { Chat };
