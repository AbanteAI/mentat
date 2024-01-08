import { useEffect, useRef } from "react"
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
    const backgroundColor =
      chatMessage.source === "client"
        ? "bg-[var(--vscode-input-background)]"
        : ""

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
        {content}
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
