import { ReactNode, useEffect, useState } from "react"

import { ChatMessage, StreamMessage, LanguageServerMessage } from "../../types"
import { vscode } from "../utils/vscode"
import ChatHistory from "../components/ChatHistory"

import ChatInput from "../components/ChatInput"

function Chat() {
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([])
  const [inputRequestId, setInputRequestId] = useState<string | null>(null)

  function handleStreamMessage(message: StreamMessage) {
    const messageEnd: string =
      message.extra?.end === undefined ? "\n" : message.extra?.end
    const messageColor: string =
      message.extra?.color === undefined ? null : message.extra?.color
    const messageStyle: string =
      message.extra?.style === undefined ? null : message.extra?.style

    setChatMessages((prevChatMessages) => {
      // Create first message
      if (prevChatMessages.length === 0) {
        const newChatMessage: ChatMessage = {
          id: 0,
          content: message.data + messageEnd,
          source: message.source,
          color: messageColor,
          style: messageStyle,
        }
        return [newChatMessage]
      }
      // Update or Create message
      else {
        const lastIndex = prevChatMessages.length - 1
        const lastMessage = { ...prevChatMessages[lastIndex] }
        // Update last message content if the last message is from the server
        if (lastMessage.source === "server") {
          lastMessage.content = lastMessage.content + message.data + messageEnd
          const updatedChatMessages = [...prevChatMessages]
          updatedChatMessages[lastIndex] = lastMessage
          return updatedChatMessages
        }
        // Create new message if the last message is from the client
        else {
          const newChatMessage: ChatMessage = {
            id: lastMessage.id + 1,
            content: message.data + messageEnd,
            source: message.source,
            color: messageColor,
            style: messageStyle,
          }
          return [...prevChatMessages, newChatMessage]
        }
      }
    })
  }

  function handleLanguageServerMessage(
    event: MessageEvent<LanguageServerMessage>
  ) {
    const message = event.data
    console.log(`Webview got message from LanguageServer: ${message}`)

    switch (message.method) {
      case "mentat/serverMessage":
        handleStreamMessage(message.data)
        break
      case "mentat/inputRequest":
        setInputRequestId(message.data.id)
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
      <div className="flex flex-col justify-between h-full">
        <ChatHistory chatMessages={chatMessages} />
        <ChatInput
          chatMessages={chatMessages}
          setChatMessages={setChatMessages}
          inputRequestId={inputRequestId}
        />
      </div>
    </div>
  )
}

export default Chat
