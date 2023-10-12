import { useState } from "react";

import { ChatMessage } from "../types";
import { ChatHistory } from "./ChatHistory";
import { ChatInput } from "./ChatInput";

const fakeMessages: ChatMessage[] = [
  {
    id: "1",
    content: "I'm using Mentat",
    createdBy: "client",
  },
];

function Chat() {
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>(fakeMessages);

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
