type ChatMessage = {
  id: string;
  orderId: number;
  content: string;
  createdBy: "client" | "server";
};

type LanguageClientMessage = {
  command: string;
  data: ChatMessage;
};

export { LanguageClientMessage, ChatMessage };
