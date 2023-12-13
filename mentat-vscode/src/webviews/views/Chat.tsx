import { useEffect, useState } from "react"

import { ChatMessage, LanguageServerMessage, ChatMessageSender } from "../../types"
import { vscode } from "../utils/vscode"
import ChatHistory from "../components/ChatHistory"

import ChatInput from "../components/ChatInput"

function Chat() {
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([])

  function handleLanguageServerMessage(event: MessageEvent<LanguageServerMessage>) {
    const message = event.data
    console.log(`Webview got message from LanguageServer: ${message}`)

    switch (message.method) {
      case "mentat/echoInput":
        setChatMessages((prevChatMessages) => {
          if (prevChatMessages.length === 0) {
            const newChatMessage: ChatMessage = {
              id: "0",
              orderId: 0,
              content: message.data,
              createdBy: ChatMessageSender.Server,
            }
            return [newChatMessage]
          } else {
            const lastIndex = prevChatMessages.length - 1
            const lastMessage = { ...prevChatMessages[lastIndex] } // Create a copy of the last message
            if (lastMessage.createdBy === ChatMessageSender.Server) {
              lastMessage.content = lastMessage.content + message.data // Update the copy, not the original
              const updatedChatMessages = [...prevChatMessages] // Create a copy of the array
              updatedChatMessages[lastIndex] = lastMessage // Update the copy of the array
              return updatedChatMessages // Return the updated copy
            } else {
              const newChatMessage: ChatMessage = {
                id: "",
                orderId: lastMessage.orderId + 1,
                content: message.data,
                createdBy: ChatMessageSender.Server,
              }
              return [...prevChatMessages, newChatMessage]
            }
          }
        })
        break
      default:
        console.log(`Unhandled LanguageServerMessage method ${message.method}`)
        break
    }
  }

  useEffect(() => {
    window.addEventListener("message", handleLanguageServerMessage)
    return () => {
      window.removeEventListener("message", handleLanguageServerMessage)
    }
  }, [])

  return (
    <div className="h-screen">
      <div className="flex flex-col p-1 h-full">
        <ChatHistory chatMessages={chatMessages} />
        <ChatInput chatMessages={chatMessages} setChatMessages={setChatMessages} />
      </div>
    </div>
  )
}

export default Chat
