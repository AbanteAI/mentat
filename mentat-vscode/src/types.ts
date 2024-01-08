import { ReactNode } from "react"

type StreamMessage = {
  id: string
  channel: string
  source: "server" | "client"
  data: any
  extra: { [key: string]: any }
  created_at: string
}

type ChatMessage = {
  id: number
  content: string
  source: "client" | "server"
}

type LanguageServerMessage = {
  type: "notification" | "request" | "command"
  method:
    | "mentat/serverMessage"
    | "mentat/clientMessage"
    | "mentat/inputRequest"
  data: any
}

export { ChatMessage, StreamMessage, LanguageServerMessage }
