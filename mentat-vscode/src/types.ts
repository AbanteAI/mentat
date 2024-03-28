type StreamMessage = {
    id: string;
    channel: string;
    source: "server" | "client";
    data: any;
    extra: { [key: string]: any };
};

type MessageContent = {
    text: string;
    style?: string;
    color?: string;
    filepath?: string;
    filepath_display?: [string, "creation" | "deletion" | "rename" | "edit"];
    delimiter?: boolean;
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
    git_diff_paths: string[];
    total_tokens: number;
    maximum_tokens: number;
    total_cost: number;
};

type FileEdit = {
    file_path: string;
    new_file_path?: string;
    type: "edit" | "creation" | "deletion";
    new_content: string;
};

export { Message, MessageContent, StreamMessage, ContextUpdateData, FileEdit };
