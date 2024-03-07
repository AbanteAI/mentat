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

type ContextUpdateData = {
    cwd: string;
    diff_context_display: string;
    auto_context_tokens: number;
    features: string[];
    auto_features: string[];
    git_diff_paths: string[];
    total_tokens: number;
    total_cost: number;
};

export { Message, MessageContent, StreamMessage, ContextUpdateData };
