import React, { useEffect, useRef, useState } from "react";

import { Message, StreamMessage } from "../../types";

import ChatInput from "../components/ChatInput";
import ChatMessage from "webviews/components/ChatMessage";
import { vscode } from "webviews/utils/vscode";
import { v4 } from "uuid";

export default function Chat() {
    const [messages, setMessages] = useState<Message[]>([]);
    const [inputRequestId, setInputRequestId] = useState<string | undefined>(
        undefined
    );
    const chatLogRef = useRef<HTMLDivElement>(null);

    const scrollToBottom = () => {
        if (chatLogRef.current) {
            chatLogRef.current.scrollTop = chatLogRef.current.scrollHeight;
        }
    };
    useEffect(() => {
        scrollToBottom();
    }, [messages]);

    function addMessage(message: Message) {
        setMessages((prevMessages) => {
            // If the last message was from the same source, merge the messages
            // TODO: Merge same color contents as well (so that additions and removals don't add hundreds of spans)
            const lastMessage = prevMessages.at(-1);
            if (message.source === lastMessage?.source) {
                return [
                    ...prevMessages.slice(0, -1),
                    {
                        ...lastMessage,
                        content: [...lastMessage.content, ...message.content],
                    },
                ];
            } else {
                return [...prevMessages, message];
            }
        });
    }

    function handleDefaultMessage(message: StreamMessage) {
        const messageEnd: string =
            message.extra?.end === undefined ? "\n" : message.extra?.end;
        const messageColor: string =
            message.extra?.color === undefined
                ? undefined
                : message.extra?.color;
        // TODO: Use style (make a map somewhere like we have in the client)
        const messageStyle: string =
            message.extra?.style === undefined
                ? undefined
                : message.extra?.style;

        addMessage({
            content: [{ text: message.data + messageEnd, color: messageColor }],
            source: "mentat",
        });
    }

    function handleServerMessage(event: MessageEvent<StreamMessage>) {
        console.log("HEY", event.data);
        const message = event.data;
        switch (message.channel) {
            case "default": {
                handleDefaultMessage(message);
                break;
            }
            case "input_request": {
                setInputRequestId(message.id);
                break;
            }
            default: {
                console.error(`Unknown message channel ${message.channel}.`);
                break;
            }
        }
    }

    useEffect(() => {
        window.addEventListener("message", handleServerMessage);
        return () => {
            window.removeEventListener("message", handleServerMessage);
        };
    }, []);

    function onUserInput(input: string) {
        addMessage({
            content: [{ text: input, color: undefined }],
            source: "user",
        });

        // Send message to webview
        const message: StreamMessage = {
            id: v4(),
            channel: `input_request:${inputRequestId}`,
            source: "client",
            data: input,
            extra: {},
        };
        vscode.postMessage(message);
    }

    // Using index as key should be fine since we never insert, delete, or re-order chat messages
    const chatMessageElements = messages.map((message, index) => (
        <React.Fragment key={index}>{ChatMessage({ message })}</React.Fragment>
    ));
    return (
        <div className="h-screen">
            <div className="flex flex-col justify-between h-full">
                <div
                    ref={chatLogRef}
                    className="flex flex-col gap-2 overflow-y-scroll hide-scrollbar"
                >
                    {chatMessageElements}
                </div>
                <ChatInput
                    onUserInput={onUserInput}
                    inputRequestId={inputRequestId}
                />
            </div>
        </div>
    );
}
