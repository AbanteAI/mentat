type ChatMessage = {
  id: string;
  orderId: number;
  content: string;
  createdBy: "client" | "server";
};

export { ChatMessage };
