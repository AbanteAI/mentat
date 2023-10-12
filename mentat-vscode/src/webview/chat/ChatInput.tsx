import { ChangeEvent, useState } from "react";
import { VscSend } from "react-icons/vsc";

import { ChatMessage } from "../types";

type Props = {
  chatMessages: ChatMessage[];
  setChatMessages: (chatMessages: ChatMessage[]) => void;
};

function ChatInput(props: Props) {
  const [content, setContent] = useState<string>("");
  const [submitDisabled] = useState(true);

  function handleContentChange(event: ChangeEvent<HTMLTextAreaElement>) {
    setContent(event.target.value);
  }

  function handleSubmit() {
    const newChatMessage: ChatMessage = {
      id: "",
      content: content,
      createdBy: "client",
    };
    props.setChatMessages([...props.chatMessages, newChatMessage]);
    setContent("");
  }

  return (
    <div className="flex flex-row border border-red-500 bg-[var(--vscode-input-background)] p-2">
      <textarea
        className="flex-1 focus:outline-none resize-none bg-[var(--vscode-input-background)]"
        placeholder="What can I do for you?"
        style={{ scrollbarWidth: "none", msOverflowStyle: "none" }}
        value={content}
        onChange={handleContentChange}
      />
      <button onClick={handleSubmit}>
        <VscSend size={18} />
      </button>
    </div>
  );
}

export { ChatInput };
