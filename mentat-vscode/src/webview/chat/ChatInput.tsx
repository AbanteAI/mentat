import { ChangeEvent, KeyboardEvent, useEffect, useState } from "react";
import { VscSend } from "react-icons/vsc";

import { ChatMessage } from "../types";

type Props = {
  chatMessages: ChatMessage[];
  setChatMessages: (chatMessages: ChatMessage[]) => void;
};

function ChatInput(props: Props) {
  const [content, setContent] = useState<string>("");
  const [submitDisabled, setSubmitDisabled] = useState(true);

  useEffect(() => {
    if (content === "") {
      setSubmitDisabled(true);
    } else {
      setSubmitDisabled(false);
    }
  }, [content]);

  function handleSubmit() {
    if (submitDisabled) {
      return;
    }
    const newChatMessage: ChatMessage = {
      id: "",
      orderId: props.chatMessages[props.chatMessages.length - 1].orderId + 1,
      content: content,
      createdBy: "client",
    };
    props.setChatMessages([...props.chatMessages, newChatMessage]);
    setContent("");
  }

  function handleKeyPress(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      handleSubmit();
    }
  }

  return (
    <div className="flex flex-row border border-red-500 bg-[var(--vscode-input-background)] p-2">
      <textarea
        className="flex-1 focus:outline-none resize-none bg-[var(--vscode-input-background)]"
        placeholder="What can I do for you?"
        style={{ scrollbarWidth: "none", msOverflowStyle: "none" }}
        value={content}
        onKeyDown={handleKeyPress}
        onChange={(e) => setContent(e.target.value)}
      />
      <button
        className={`${submitDisabled
            ? "bg-none"
            : "bg-[var(--vscode-button-background)] hover:bg-[var(--vscode-button-hoverBackground)]"
          } w-10 h-10 flex justify-center items-center rounded-lg`}
        onClick={handleSubmit}
        disabled={submitDisabled}
      >
        <VscSend
          color={
            submitDisabled
              ? "var(--vscode-disabledForeground)"
              : "var(--vscode-button-foreground)"
          }
          size={18}
        />
      </button>
    </div>
  );
}

export { ChatInput };
