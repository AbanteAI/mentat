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

enum LanguageServerMethod {
  GetInput = "mentat/getInput",
  CreateSession = "mentat/createSession",
  StreamSession = "mentat/streamSession",
}

type LanguageServerRequest = {
  id: string;
  method: LanguageServerMethod;
  data: MentatSessionStreamMessage;
};

type LanguageServerNotification = {
  method: LanguageServerMethod;
  data: MentatSessionStreamMessage;
};

type LanguageClientMessage = {
  method: LanguageServerMethod;
  data?: any;
};

export {
  ChatMessage,
  ChatMessageSender,
  LanguageClientMessage,
  LanguageServerRequest,
  LanguageServerMethod,
  LanguageServerNotification,
};
