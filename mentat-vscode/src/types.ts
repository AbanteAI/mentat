type StreamMessage = {
    id: string;
    channel: string;
    source: "server" | "client";
    data: any;
    extra: { [key: string]: any };
};

type MessageContent = {
    text: string;
    style: string | undefined;
    color: string | undefined;
};

type Message = {
    content: MessageContent[];
    source: "user" | "mentat";
};

export { Message, MessageContent, StreamMessage };
