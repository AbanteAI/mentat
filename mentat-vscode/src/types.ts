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

//
// enum MentatLanguageServerFeature {
//   CreateSession = "mentat/createSession",
//   InputRequest = "mentat/inputRequest",
// }
//
// type MentatLanguageServerMessage = {
//   feature: MentatLanguageServerFeature;
//   data: MentatSessionStreamMessage;
// };
//
// type MentatClientMessage = {
//   channel: string;
//   data: any;
//   extra?: any;
//   created_at: Date;
// };

// enum LanguageServerFeature {
//   CreateSession = "mentat/createSession",
//   InputRequest = "mentat/inputRequest",
// }

enum LanguageServerMethod {
  InputRequest = "mentat/inputRequest",
  SessionCreate = "mentat/sessionCreate",
  SessionOutput = "mentat/sessionOutput",
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
