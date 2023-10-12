type ChatMessage = {
  id: string;
  content: string;
  createdBy: "client" | "server";
};

export { ChatMessage };
