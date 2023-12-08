import { useEffect, useState } from "react";

import {
  ChatMessage,
  ChatMessageSender,
  LanguageServerMethod,
  LanguageServerNotification,
  LanguageServerRequest,
} from "../../types";
import { vscode } from "../utils/vscode";
import { ChatHistory } from "../components/ChatHistory";
import { ChatInput } from "../components/ChatInput";

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
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [inputRequestId, setInputRequestId] = useState<string | null>(null);

  function handleLanguageServerMessage(
    event:
      | MessageEvent<LanguageServerNotification>
      | MessageEvent<LanguageServerRequest>
  ) {
    const message = event.data;
    console.log(`React got message from LanguageServer: ${message}`);

    // switch (message.method) {
    //   case LanguageServerMethod.GetInput:
    //     setInputRequestId(message.data.id);
    //     break;
    //   case LanguageServerMethod.StreamSession:
    //     setChatMessages((prevChatMessages) => {
    //       if (prevChatMessages.length === 0) {
    //         const newChatMessage: ChatMessage = {
    //           id: "0",
    //           orderId: 0,
    //           content: message.data.data,
    //           createdBy: ChatMessageSender.Server,
    //         };
    //         return [newChatMessage];
    //       } else {
    //         const lastIndex = prevChatMessages.length - 1;
    //         const lastMessage = { ...prevChatMessages[lastIndex] }; // Create a copy of the last message
    //         if (lastMessage.createdBy === ChatMessageSender.Server) {
    //           lastMessage.content = lastMessage.content + message.data.data; // Update the copy, not the original
    //           const updatedChatMessages = [...prevChatMessages]; // Create a copy of the array
    //           updatedChatMessages[lastIndex] = lastMessage; // Update the copy of the array
    //           return updatedChatMessages; // Return the updated copy
    //         } else {
    //           const newChatMessage: ChatMessage = {
    //             id: "",
    //             orderId: lastMessage.orderId + 1,
    //             content: message.data.data,
    //             createdBy: ChatMessageSender.Server,
    //           };
    //           return [...prevChatMessages, newChatMessage];
    //         }
    //       }
    //     });
    //     break;
    //   default:
    //     console.log(`Unhandled LanguageServerMethod ${message.method}`);
    //     break;
    // }
  }

  useEffect(() => {
    window.addEventListener("message", handleLanguageServerMessage);

    // vscode.postMessage({
    //   method: LanguageServerMethod.CreateSession,
    // });

    return () => {
      window.removeEventListener("message", handleLanguageServerMessage);
    };
  }, []);

  return (
    <div className="h-screen">
      <div className="flex flex-col p-1 h-full">
        {/* <ChatHistory chatMessages={chatMessages} />
        <ChatInput
          chatMessages={chatMessages}
          setChatMessages={setChatMessages}
          inputRequestId={inputRequestId}
          setInputRequestId={setInputRequestId}
        /> */}
      </div>
    </div>
  );
}

export default Chat;
