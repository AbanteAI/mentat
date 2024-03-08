import React, { useEffect, useRef, useState } from "react";

import { Message, MessageContent, StreamMessage } from "../../types";

import ChatInput from "../components/ChatInput";
import ChatMessage from "webviews/components/ChatMessage";
import { vscode } from "webviews/utils/vscode";

export default function Chat() {
    const [messages, setMessages] = useState<Message[]>([]);
    const [inputRequestId, setInputRequestId] = useState<string | undefined>(
        undefined
    );
    const [sessionActive, setSessionActive] = useState<boolean>(true);
    const [textAreaValue, setTextAreaValue] = useState<string>("");
    const [interruptable, setInterruptable] = useState<boolean>(false);
    const chatLogRef = useRef<HTMLDivElement>(null);

    // TODO: Rarely, if you move fast during model output, some bugs can occur when reloading webview view;
    // figure out why and fix it (easiest to see if you turn off retainContextWhenHidden). Once fixed, turn off retainContextWhenHidden permanently.
    // Also TODO: When restarting vscode during model output, interruptable will be stuck on (along with a few other quirks).

    // Whenever you add more state, make certain to update both of these effects!!!
    useEffect(() => {
        const state: any = vscode.getState();
        if (state !== undefined) {
            setMessages(state.messages);
            setInputRequestId(state.inputRequestId);
            setSessionActive(state.sessionActive);
            setTextAreaValue(state.textAreaValue);
            setInterruptable(state.interruptable);
        }
    }, []);
    useEffect(() => {
        const state = {
            messages,
            inputRequestId,
            sessionActive,
            textAreaValue,
            interruptable,
        };
        vscode.setState(state);
    }, [messages, inputRequestId, sessionActive, textAreaValue, interruptable]);

    const scrollToBottom = () => {
        if (chatLogRef.current) {
            chatLogRef.current.scrollTop = chatLogRef.current.scrollHeight;
        }
    };
    useEffect(() => {
        scrollToBottom();
    }, [messages]);

    function addMessageContent(
        messageContent: MessageContent,
        source: "user" | "mentat"
    ) {
        setMessages((prevMessages) => {
            // If the last message was from the same source, merge the messages
            const lastMessage = prevMessages.at(-1);
            if (source === lastMessage?.source) {
                const { text: lastText, ...lastAttributes } =
                    lastMessage.content.at(-1) ?? {
                        text: "",
                        style: undefined,
                        color: undefined,
                    };
                const { text: curText, ...curAttributes } = messageContent;
                // If the last 2 message contents have the same attributes, merge them to avoid creating hundreds of spans, and also to create specific style/edit 'boxes'
                let newLastMessage;
                if (lastAttributes === curAttributes) {
                    newLastMessage = {
                        ...lastMessage,
                        content: [
                            ...lastMessage.content.slice(0, -1),
                            { text: lastText + curText, ...lastAttributes },
                        ],
                    };
                } else {
                    newLastMessage = {
                        ...lastMessage,
                        content: [...lastMessage.content, messageContent],
                    };
                }
                return [...prevMessages.slice(0, -1), newLastMessage];
            } else {
                return [
                    ...prevMessages,
                    { content: [messageContent], source: source },
                ];
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
        const messageStyle: string =
            message.extra?.style === undefined
                ? undefined
                : message.extra?.style;

        addMessageContent(
            {
                text: message.data + messageEnd,
                style: messageStyle,
                color: messageColor,
            },
            "mentat"
        );
    }

    function handleServerMessage(event: MessageEvent<StreamMessage>) {
        const message = event.data;
        switch (message.channel.split(":").at(0)) {
            case "default": {
                handleDefaultMessage(message);
                break;
            }
            case "client_exit": {
                // In other clients, this would mean quit; in VSCode, we obviously don't want to shut off VSCode so we don't actually do anything.
                break;
            }
            case "session_stopped": {
                setSessionActive(false);
                break;
            }
            case "loading": {
                // TODO: Add loading bar
                break;
            }
            case "input_request": {
                setInputRequestId(message.id);
                break;
            }
            case "edits_complete": {
                // Not needed for this client
                break;
            }
            case "completion_request": {
                const message_id = message.channel.split(":").at(1);
                break;
            }
            case "default_prompt": {
                setTextAreaValue(message.data);
                break;
            }
            case "interruptable": {
                setInterruptable(message.data);
                break;
            }
            case "context_update": {
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
        // If we send messages before the webview loads and we add the listener, they get thrown out,
        // so we have to signal when we're loaded and can recieve the stored messages.
        vscode.sendMessage(null, "vscode:webview_loaded");
        return () => {
            window.removeEventListener("message", handleServerMessage);
        };
    }, []);

    function onUserInput(input: string) {
        addMessageContent(
            { text: input, style: undefined, color: undefined },
            "user"
        );
        // Send message to webview
        vscode.sendMessage(input, `input_request:${inputRequestId}`);
    }

    function onCancel() {
        vscode.sendMessage(null, "interrupt");
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
                    sessionActive={sessionActive}
                    textAreaValue={textAreaValue}
                    setTextAreaValue={setTextAreaValue}
                    cancelEnabled={interruptable}
                    onCancel={onCancel}
                />
            </div>
        </div>
    );
}
