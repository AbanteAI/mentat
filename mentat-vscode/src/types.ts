enum ChatMessageSender {
  Client,
  Server,
}

type ChatMessage = {
  id: string
  orderId: number
  content: string
  createdBy: ChatMessageSender
}

type LanguageServerMessage = {
  type: "notification" | "request" | "command"
  method: "mentat/echoInput"
  data: any
}

export { ChatMessage, ChatMessageSender, LanguageServerMessage }
