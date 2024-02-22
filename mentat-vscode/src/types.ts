type StreamMessage = {
    id: string;
    channel: string;
    source: "server" | "client";
    data: any;
    extra: { [key: string]: any };
    created_at: string;
};

type MessageContent = {
    text: string;
    color: string | undefined;
};

type Message = {
    content: MessageContent[];
    source: "user" | "mentat";
};

export { Message, MessageContent, StreamMessage };
