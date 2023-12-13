import { useEffect, useRef } from "react";
import { VscAccount } from "react-icons/vsc";

import { ChatMessage, ChatMessageSender } from "../../types";
import MentatIcon from "./MentatIcon";

type Props = {
  chatMessages: ChatMessage[];
};

export default function ChatHistory(props: Props) {
  const chatHistoryRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    if (chatHistoryRef.current) {
      chatHistoryRef.current.scrollTop = chatHistoryRef.current.scrollHeight;
    }
  };

  useEffect(() => {
    scrollToBottom();
  }, [props.chatMessages]);

  const chatMessageCards = props.chatMessages.map((chatMessage) => {
    const backgroundColor =
      chatMessage.createdBy === ChatMessageSender.Client
        ? "bg-[var(--vscode-input-background)]"
        : "";

    const messageIcon =
      chatMessage.createdBy === ChatMessageSender.Client ? (
        <VscAccount size={18} />
      ) : (
        <MentatIcon />
      );

    return (
      <div
        key={chatMessage.orderId}
        className={`flex items-center p-2 ${backgroundColor}`}
      >
        {messageIcon}
        <p className="flex-1 pl-2">{chatMessage.content}</p>
      </div>
    );
  });

  return (
    <div ref={chatHistoryRef} className="flex-1 overflow-y-scroll">
      {chatMessageCards}
    </div>
  );
}

