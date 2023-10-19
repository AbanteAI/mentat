import { useEffect, useState } from "react";

import {
  ChatMessage,
  ChatMessageSender,
  MentatLanguageServerMessage,
  MentatSessionStreamMessage,
} from "../../types";
import { vscode } from "../utils/vscode";
import { ChatHistory } from "./ChatHistory";
import { ChatInput } from "./ChatInput";

const fakeMessages: ChatMessage[] = [
  {
    id: "0",
    orderId: 0,
    content: "I'm using Mentat",
    createdBy: ChatMessageSender.Client,
  },
  {
    id: "1",
    orderId: 1,
    content: "This is a server message",
    createdBy: ChatMessageSender.Server,
  },
  {
    id: "2",
    orderId: 2,
    content: "Whoa this is another chat message!",
    createdBy: ChatMessageSender.Client,
  },
];

function Chat() {
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>(fakeMessages);
  const [inputRequest, setInputRequest] = useState<MentatSessionStreamMessage | null>(
    null
  );

  function handleMessage(payload: MessageEvent<MentatLanguageServerMessage>) {
    console.log(`React got message from Extension: ${payload}`);
    const message = payload.data.data;
    if (message.channel === "input_request") {
      setInputRequest(message);
    } else if (message.channel === "default") {
      setChatMessages((prevMessages) => {
        if (prevMessages.length === 0) {
          const newChatMessage: ChatMessage = {
            id: "",
            orderId: prevMessages[prevMessages.length - 1].orderId + 1,
            content: message.data,
            createdBy: ChatMessageSender.Server,
          };
          return [newChatMessage];
        }

        const lastMessageIndex = prevMessages.length - 1;
        if (prevMessages[lastMessageIndex].createdBy === ChatMessageSender.Server) {
          prevMessages[lastMessageIndex].content =
            prevMessages[lastMessageIndex].content + message.data;
          return [...prevMessages];
        } else {
          const newChatMessage: ChatMessage = {
            id: "",
            orderId: prevMessages[prevMessages.length - 1].orderId + 1,
            content: message.data,
            createdBy: ChatMessageSender.Server,
          };
          return [...prevMessages, newChatMessage];
        }
      });
    }
  }

  useEffect(() => {
    window.addEventListener("message", handleMessage);

    return () => {
      window.removeEventListener("message", handleMessage);
    };
  }, []);

  // useEffect(() => {
  //   vscode.postMessage({ command: "mentat/chatMessage", data: chatMessages });
  // }, [chatMessages]);

  return (
    <div className="border border-red-500 h-screen">
      <div className="flex flex-col border border-green-500 p-1 h-full">
        <ChatHistory chatMessages={chatMessages} />
        <ChatInput
          chatMessages={chatMessages}
          setChatMessages={setChatMessages}
          inputRequest={inputRequest}
          setInputRequest={setInputRequest}
        />
      </div>
    </div>
  );
}

export { Chat };
