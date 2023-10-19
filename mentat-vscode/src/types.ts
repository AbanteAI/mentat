enum ChatMessageSender {
  Client,
  Server,
}

type ChatMessage = {
  id: string;
  orderId: number;
  content: string;
  createdBy: ChatMessageSender;
};

enum MentatSessionStreamMessageSource {
  Client = "client",
  Server = "server",
}

type MentatSessionStreamMessage = {
  id: string;
  channel: string;
  source: MentatSessionStreamMessageSource;
  data: any;
  extra?: any;
  created_at: string;
};

type MentatLanguageServerMessage = {
  type: "input_request";
  data: MentatSessionStreamMessage;
};

type MentatClientMessage = {
  channel: string;
  data: any;
  extra?: any;
  created_at: Date;
};

export {
  ChatMessage,
  ChatMessageSender,
  MentatSessionStreamMessage,
  MentatLanguageServerMessage,
  MentatClientMessage,
};
