import { VscAccount } from "react-icons/vsc";

import { ChatMessage } from "../types";

type Props = {
  chatMessages: ChatMessage[];
};

function ChatHistory(props: Props) {
  const chatMessageCards = props.chatMessages.map((chatMessage) => {
    const backgroundColor =
      chatMessage.createdBy === "client" ? "bg-[var(--vscode-input-background)]" : "";

    return (
      <div key={chatMessage.id} className={`flex items-center p-2 ${backgroundColor}`}>
        <VscAccount size={18} />
        <p className="flex-1 pl-2">{chatMessage.content}</p>
      </div>
    );
  });

  return (
    <div className="flex-1 border border-purple-400">
      <h1>History</h1>
      {chatMessageCards}
    </div>
  );
}

export { ChatHistory };
