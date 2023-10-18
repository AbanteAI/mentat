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
    content: "This is a server message",
    createdBy: "server",
  },
  {
    id: "2",
    orderId: 2,
    content: "Whoa this is another chat message!",
    createdBy: "client",
  },
];

function Chat() {
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>(fakeMessages);

  function handleMessage(payload: any) {
    console.log(`Webview got message from Extension: ${payload}`);
    setChatMessages((prevMessages) => {
      const newChatMessage: ChatMessage = {
        id: "",
        orderId: prevMessages[prevMessages.length - 1].orderId + 1,
        content: "hello from the server!",
        createdBy: "server",
      };
      return [...prevMessages, newChatMessage];
    });
  }

  useEffect(() => {
    window.addEventListener("message", handleMessage);
    return () => {
      window.removeEventListener("message", handleMessage);
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
