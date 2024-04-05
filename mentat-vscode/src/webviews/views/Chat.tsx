import React, { useEffect, useRef, useState } from "react";

import {
    ContextUpdateData,
    FileEdit,
    Message,
    MessageContent,
    StreamMessage,
} from "../../types";

import ChatInput from "webviews/components/ChatInput";
import ChatMessage from "webviews/components/ChatMessage";
import { vscode } from "webviews/utils/vscode";
import { isEqual } from "lodash";
import { WorkspaceRootContext } from "webviews/context/WorkspaceRootContext";
import CostOverview from "webviews/components/CostOverview";
import WarningIcon from "webviews/components/WarningIcon";

const MESSAGE_LIMIT = 100;

export default function Chat() {
    // We have to use null instead of undefined everywhere here because vscode.setState serializes into json, so getState turns undefined into null
    const [previousMessages, setPreviousMessages] = useState<Message[]>([]);
    const [messages, setMessages] = useState<Message[]>([]);
    const [inputRequestId, setInputRequestId] = useState<string | null>(null);
    const [sessionActive, setSessionActive] = useState<boolean>(true);
    const [textAreaValue, setTextAreaValue] = useState<string>("");
    const [interruptable, setInterruptable] = useState<boolean>(false);
    const [activeEdits, setActiveEdits] = useState<FileEdit[]>([]);
    const [workspaceRoot, setWorkspaceRoot] = useState<string>("");
    const [contextUpdataData, setContextUpdateData] =
        useState<ContextUpdateData>();

    const [loaded, setLoaded] = useState<boolean>(false);

    const chatLogRef = useRef<HTMLDivElement>(null);

    // TODO: Rarely, if you move fast during model output, some bugs can occur when reloading webview view;
    // figure out why and fix it (easiest to see if you turn off retainContextWhenHidden). Once fixed, turn off retainContextWhenHidden permanently.

    useEffect(() => {
        window.addEventListener("message", handleServerMessage);
        // If we send messages before the webview loads and we add the listener, they get thrown out,
        // so we have to signal when we're loaded and can recieve the stored messages.
        vscode.sendMessage(null, "vscode:webviewLoaded");
        return () => {
            window.removeEventListener("message", handleServerMessage);
        };
    }, []);
    // Whenever you add more state, make certain to update this effect and the continuingSession message receiver!
    useEffect(() => {
        if (loaded) {
            const state = {
                previousMessages,
                messages,
                inputRequestId,
                sessionActive,
                textAreaValue,
                interruptable,
                activeEdits,
                workspaceRoot,
                contextUpdataData,
            };
            vscode.setState(state);
        }
    }, [
        previousMessages,
        messages,
        inputRequestId,
        sessionActive,
        textAreaValue,
        interruptable,
        activeEdits,
        workspaceRoot,
        contextUpdataData,
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
            // If the last 2 messages were both from mentat, merge the messages
            const lastMessage = prevMessages.at(-1);
            if (source === "mentat" && lastMessage?.source === "mentat") {
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
                setContextUpdateData(message.data);
                break;
            }
            case "vscode": {
                const subchannel = message.channel.split(":").at(1);
                switch (subchannel) {
                    case "newSession": {
                        setLoaded(true);
                        const state: any = vscode.getState();
                        const statePreviousMessages: Message[] =
                            state.previousMessages ?? [];
                        const stateMessages: Message[] = state.messages ?? [];
                        if (
                            stateMessages.some(
                                (message) => message.source === "user"
                            )
                        ) {
                            setPreviousMessages([
                                ...statePreviousMessages,
                                ...stateMessages,
                            ]);
                        } else {
                            setPreviousMessages(statePreviousMessages);
                        }

                        setMessages([
                            {
                                content: [
                                    {
                                        text: "What can I do for you?\n",
                                        style: "info",
                                    },
                                ],
                                source: "mentat",
                            },
                        ]);
                        setWorkspaceRoot(message.extra.workspaceRoot);
                        break;
                    }
                    case "continuingSession": {
                        setLoaded(true);
                        const state: any = vscode.getState();
                        if (state) {
                            setPreviousMessages(state.previousMessages ?? []);
                            setMessages(state.messages ?? []);
                            setInputRequestId(state.inputRequestId ?? null);
                            setSessionActive(state.sessionActive ?? true);
                            setTextAreaValue(state.textAreaValue ?? "");
                            setInterruptable(state.interruptable ?? false);
                            setActiveEdits(state.activeEdits ?? []);
                            setWorkspaceRoot(state.workspaceRoot ?? "");
                            setContextUpdateData(state.contextUpdataData ?? {});
                        }
                        break;
                    }
                    case "clearChatbox": {
                        setPreviousMessages([]);
                        setMessages([
                            {
                                content: [
                                    {
                                        text: "What can I do for you?\n",
                                        style: "info",
                                    },
                                ],
                                source: "mentat",
                            },
                        ]);
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
    const previousMessageElements = previousMessages.map(
        (message, index, arr) => (
            <React.Fragment key={index}>
                <ChatMessage
                    message={message}
                    activeEdits={[]}
                    onAccept={onAccept}
                    onDecline={onDecline}
                    onPreview={onPreview}
                ></ChatMessage>
            </React.Fragment>
        )
    );
    const chatMessageElements = messages.map((message, index, arr) => (
        <React.Fragment key={index}>
            <ChatMessage
                message={message}
                activeEdits={index === arr.length - 1 ? activeEdits : []}
                onAccept={onAccept}
                onDecline={onDecline}
                onPreview={onPreview}
            ></ChatMessage>
        </React.Fragment>
    ));
    return (
        <WorkspaceRootContext.Provider value={workspaceRoot}>
            <div
                className="h-screen relative"
                style={{
                    fontWeight: "var(--vscode-editor-font-weight)",
                    fontSize: "var(--vscode-editor-font-size)",
                }}
            >
                <div className="flex flex-col grow justify-between h-full">
                    <div
                        ref={chatLogRef}
                        className="flex flex-col gap-2 overflow-y-scroll"
                    >
                        {previousMessageElements}
                        {previousMessages.length > 0 && (
                            <fieldset className="w-full border-t-2">
                                <legend className="mx-auto px-1">
                                    Conversation above this point not included
                                    in chat context
                                </legend>
                            </fieldset>
                        )}
                        {chatMessageElements}
                    </div>
                    {!sessionActive && (
                        <div className="bg-[var(--vscode-problemsErrorIcon-foreground)] p-2 my-2 rounded-md w-fit flex gap-2 text-white">
                            <WarningIcon />
                            Mentat has crashed. Restart to re-enable Mentat.
                        </div>
                    )}
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
                <div className="w-fit h-fit absolute right-0 top-0 border-l-2 border-b-2 rounded-bl-md pl-2 pb-2 bg-[var(--vscode-activityBar-background)]">
                    <CostOverview
                        tokens_used={contextUpdataData?.total_tokens ?? 0}
                        max_tokens={contextUpdataData?.maximum_tokens ?? 0}
                        total_cost={contextUpdataData?.total_cost ?? 0}
                    ></CostOverview>
                </div>
            </div>
        </WorkspaceRootContext.Provider>
    );
}
