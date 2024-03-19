import React, { createContext, useEffect, useRef, useState } from "react";

import { FileEdit, Message, MessageContent, StreamMessage } from "../../types";

import ChatInput from "webviews/components/ChatInput";
import ChatMessage from "webviews/components/ChatMessage";
import { vscode } from "webviews/utils/vscode";
import { isEqual } from "lodash";
import { WorkspaceRootContext } from "webviews/context/WorkspaceRootContext";

const MESSAGE_LIMIT = 100;

export default function Chat() {
    // We have to use null instead of undefined everywhere here because vscode.setState serializes into json, so getState turns undefined into null
    const [messages, setMessages] = useState<(Message | null)[]>([]);
    const [inputRequestId, setInputRequestId] = useState<string | null>(null);
    const [sessionActive, setSessionActive] = useState<boolean>(true);
    const [textAreaValue, setTextAreaValue] = useState<string>("");
    const [interruptable, setInterruptable] = useState<boolean>(false);
    const [activeEdits, setActiveEdits] = useState<FileEdit[]>([]);
    const [workspaceRoot, setWorkspaceRoot] = useState<string>("");

    const chatLogRef = useRef<HTMLDivElement>(null);

    // TODO: Rarely, if you move fast during model output, some bugs can occur when reloading webview view;
    // figure out why and fix it (easiest to see if you turn off retainContextWhenHidden). Once fixed, turn off retainContextWhenHidden permanently.
    // Also TODO: When restarting vscode during model output, interruptable will be stuck on (along with a few other quirks).

    // Whenever you add more state, make certain to update both of these effects!!!
    useEffect(() => {
        const state: any = vscode.getState();
        if (state) {
            setMessages(state.messages);
            setInputRequestId(state.inputRequestId);
            setTextAreaValue(state.textAreaValue);
            setInterruptable(state.interruptable);
            setActiveEdits(state.activeEdits);
            setWorkspaceRoot(state.workspaceRoot);
        }

        window.addEventListener("message", handleServerMessage);
        // If we send messages before the webview loads and we add the listener, they get thrown out,
        // so we have to signal when we're loaded and can recieve the stored messages.
        vscode.sendMessage(null, "vscode:webviewLoaded");
        return () => {
            window.removeEventListener("message", handleServerMessage);
        };
    }, []);
    useEffect(() => {
        const state = {
            messages,
            inputRequestId,
            textAreaValue,
            interruptable,
            activeEdits,
            workspaceRoot,
        };
        vscode.setState(state);
    }, [
        messages,
        inputRequestId,
        textAreaValue,
        interruptable,
        activeEdits,
        workspaceRoot,
    ]);

    const scrollToBottom = () => {
        if (chatLogRef.current) {
            chatLogRef.current.scrollTop = chatLogRef.current.scrollHeight;
        }
    };
    useEffect(() => {
        scrollToBottom();
    }, [messages, activeEdits]);

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
                    };
                const { text: curText, ...curAttributes } = messageContent;
                // If the last 2 message contents have the same attributes, merge them to avoid creating hundreds of spans, and also to create specific style/edit 'boxes'
                let newLastMessage;
                if (isEqual(lastAttributes, curAttributes)) {
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
                setActiveEdits([]);
                return [
                    ...prevMessages.slice(-(MESSAGE_LIMIT - 1)),
                    { content: [messageContent], source: source },
                ];
            }
        });
    }

    function handleDefaultMessage(message: StreamMessage) {
        const messageEnd: string = message.extra?.end ?? "\n";
        const messageColor: string | undefined = message.extra.color;
        const messageStyle: string | undefined = message.extra.style;
        const messageFilepath: string | undefined = message.extra.filepath;
        const messageFilepathDisplay:
            | [string, "creation" | "deletion" | "rename" | "edit"]
            | undefined = message.extra.filepath_display;
        const messageDelimiter: boolean = !!message.extra.delimiter;

        addMessageContent(
            {
                text: message.data + messageEnd,
                style: messageStyle,
                color: messageColor,
                filepath: messageFilepath,
                filepath_display: messageFilepathDisplay,
                delimiter: messageDelimiter,
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
            case "model_file_edits": {
                const file_edits: FileEdit[] = message.data;
                setActiveEdits(file_edits);
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
            case "vscode": {
                const subchannel = message.channel.split(":").at(1);
                switch (subchannel) {
                    case "newSession": {
                        setMessages((prevMessages) => [...prevMessages, null]);
                        setActiveEdits([]);
                        setWorkspaceRoot(message.extra.workspaceRoot);
                        break;
                    }
                    case "eraseChatHistory": {
                        setMessages([]);
                        setActiveEdits([]);
                        break;
                    }
                }
                break;
            }
            default: {
                console.error(`Unknown message channel ${message.channel}.`);
                break;
            }
        }
    }

    function onUserInput(input: string) {
        addMessageContent({ text: input }, "user");
        // Send message to webview
        vscode.sendMessage(input, `input_request:${inputRequestId}`);
    }

    function onCancel() {
        vscode.sendMessage(null, "interrupt");
    }

    function disableEdit(fileEdit: FileEdit) {
        setActiveEdits((prevActiveEdits) => {
            return prevActiveEdits.filter((edit) => edit !== fileEdit);
        });
    }

    function onAccept(fileEdit: FileEdit) {
        console.log("Accepted", fileEdit);
        disableEdit(fileEdit);
        vscode.sendMessage(fileEdit, "vscode:acceptEdit");
    }

    function onDecline(fileEdit: FileEdit) {
        disableEdit(fileEdit);
    }

    function onPreview(fileEdit: FileEdit) {
        disableEdit(fileEdit);
        vscode.sendMessage(fileEdit, "vscode:previewEdit");
    }

    // Using index as key should be fine since we never insert, delete, or re-order chat messages
    const chatMessageElements = messages.map((message, index) => (
        <React.Fragment key={index}>
            {message === null ? (
                <div className="border-solid border-b border-[var(--vscode-panel-border)]"></div>
            ) : (
                <ChatMessage
                    message={message}
                    activeEdits={
                        index === messages.length - 1 ? activeEdits : []
                    }
                    onAccept={onAccept}
                    onDecline={onDecline}
                    onPreview={onPreview}
                ></ChatMessage>
            )}
        </React.Fragment>
    ));
    return (
        <WorkspaceRootContext.Provider value={workspaceRoot}>
            <div
                className="h-screen"
                style={{
                    fontWeight: "var(--vscode-editor-font-weight)",
                    fontSize: "var(--vscode-editor-font-size)",
                }}
            >
                <div className="flex flex-col justify-between h-full">
                    <div
                        ref={chatLogRef}
                        className="flex flex-col gap-2 overflow-y-scroll"
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
        </WorkspaceRootContext.Provider>
    );
}
