import { ReactNode, useEffect, useRef } from "react"
import { VscAccount } from "react-icons/vsc"
import React from "react"

import { ChatMessage } from "../../types"
import MentatIcon from "./MentatIcon"

type Props = {
  chatMessages: ChatMessage[]
}

export default function ChatHistory(props: Props) {
  const chatHistoryRef = useRef<HTMLDivElement>(null)

  const scrollToBottom = () => {
    if (chatHistoryRef.current) {
      chatHistoryRef.current.scrollTop = chatHistoryRef.current.scrollHeight
    }
  }

  useEffect(() => {
    scrollToBottom()
  }, [props.chatMessages])

  const chatMessageCards = props.chatMessages.map((chatMessage) => {
    const sourceIcon =
      chatMessage.source === "client" ? (
        <VscAccount size={18} />
      ) : (
        <MentatIcon />
      )

    const souceName = chatMessage.source === "client" ? "You" : "Mentat"

    const splitContent = chatMessage.content.split("\n")
    const content = splitContent.map((line, index) => {
      return (
        <React.Fragment key={index}>
          {line}
          {index < splitContent.length - 1 && <br />}
        </React.Fragment>
      )
    })

    let chatMessageContent: ReactNode
    if (chatMessage.style === "error") {
      chatMessageContent = (
        <div className="bg-red-500 p-2 rounded-md flex gap-2 text-white">
          <svg
            xmlns="http://www.w3.org/2000/svg"
            fill="none"
            viewBox="0 0 24 24"
            stroke-width="1.5"
            stroke="currentColor"
            className="w-6 h-6"
          >
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              d="M12 9v3.75m9-.75a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9 3.75h.008v.008H12v-.008Z"
            />
          </svg>
          {content}
        </div>
      )
    } else if (chatMessage.style === "code") {
      chatMessageContent = (
        <div className="bg-[var(--vscode-textCodeBlock-background)]">
          {content}
        </div>
      )
    } else {
      chatMessageContent = content
    }

    return (
      <div
        key={chatMessage.id}
        className={`flex flex-col gap-2 p-2 ${
          chatMessage.id !== 0 && "border-t border-[var(--vscode-panel-border)]"
        }`}
      >
        <div className="flex gap-2 pt-2">
          {sourceIcon}
          <p className="font-bold">{souceName}</p>
        </div>
        {chatMessageContent}
      </div>
    )
  })

  return (
    <div
      ref={chatHistoryRef}
      className="flex flex-col gap-2 overflow-y-scroll hide-scrollbar"
    >
      {chatMessageCards}
    </div>
  )
}
