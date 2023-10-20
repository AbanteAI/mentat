import { useEffect, useState } from "react";

import {
  ChatMessage,
  ChatMessageSender,
  LanguageServerMethod,
  LanguageServerNotification,
  LanguageServerRequest,
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
  const [inputRequestId, setInputRequestId] = useState<string | null>(null);

  function handleLanguageServerMessage(
    event:
      | MessageEvent<LanguageServerNotification>
      | MessageEvent<LanguageServerRequest>
  ) {
    const message = event.data;
    console.log(`React got message from LanguageServer: ${message}`);

    if (message.method === LanguageServerMethod.InputRequest) {
      setInputRequestId(message.data.id);
    } else if (message.method === LanguageServerMethod.SessionOutput) {
      // // Session server output
      // if (message.channel === "default") {
      //     setChatMessages((prevMessages) => {
      //       if (prevMessages.length === 0) {
      //         const newChatMessage: ChatMessage = {
      //           id: "",
      //           orderId: prevMessages[prevMessages.length - 1].orderId + 1,
      //           content: message.data,
      //           createdBy: ChatMessageSender.Server,
      //         };
      //         return [newChatMessage];
      //       }
      //
      //       const lastMessageIndex = prevMessages.length - 1;
      //       if (prevMessages[lastMessageIndex].createdBy === ChatMessageSender.Server) {
      //         prevMessages[lastMessageIndex].content =
      //           prevMessages[lastMessageIndex].content + message.data;
      //         return [...prevMessages];
      //       } else {
      //         const newChatMessage: ChatMessage = {
      //           id: "",
      //           orderId: prevMessages[prevMessages.length - 1].orderId + 1,
      //           content: message.data,
      //           createdBy: ChatMessageSender.Server,
      //         };
      //         return [...prevMessages, newChatMessage];
      //       }
      //     });
      //   }
    }
  }

  useEffect(() => {
    window.addEventListener("message", handleLanguageServerMessage);

    vscode.postMessage({
      method: LanguageServerMethod.SessionCreate,
    });

    return () => {
      window.removeEventListener("message", handleLanguageServerMessage);
    };
  }, []);

  return (
    <div className="border border-red-500 h-screen">
      <div className="flex flex-col border border-green-500 p-1 h-full">
        <ChatHistory chatMessages={chatMessages} />
        <ChatInput
          chatMessages={chatMessages}
          setChatMessages={setChatMessages}
          inputRequestId={inputRequestId}
          setInputRequestId={setInputRequestId}
        />
      </div>
    </div>
  );
}

export { Chat };
