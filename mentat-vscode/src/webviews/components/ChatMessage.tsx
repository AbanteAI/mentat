import { VscAccount } from "react-icons/vsc";
import { Message, MessageContent } from "types";
import MentatIcon from "./MentatIcon";
import React from "react";

type Props = {
    message: Message;
};

const light_theme: { [id: string]: string } = {
    prompt: "gray",
    code: "blue",
    info: "cyan",
    failure: "darkred",
    success: "green",
    input: "lightblue",
    error: "red",
    warning: "yellow",
};
const dark_theme: { [id: string]: string } = {
    prompt: "white",
    code: "blue",
    info: "cyan",
    failure: "red",
    success: "green",
    input: "lightblue",
    error: "darkred",
    warning: "yellow",
};

function renderContentPiece(contentPiece: MessageContent, index: number) {
    return (
        <span
            // Index as key should be fine here since we never insert reorder or delete elements
            key={index}
            style={{
                color:
                    contentPiece.color ||
                    (contentPiece.style && dark_theme[contentPiece.style]),
            }}
        >
            {contentPiece.text}
        </span>
    );
}

function renderFileBlock(contentPieces: MessageContent[]) {
    return (
        <div className="border-solid rounded-md border-black border w-fit p-2 bg-[var(--vscode-mentat-fileEditBubble)]">
            {contentPieces.map(renderContentPiece)}
        </div>
    );
}

// TODO: Once everything is working, make sure to memoize!!!
export default function ChatMessage(props: Props) {
    const sourceIcon =
        props.message.source === "user" ? (
            <VscAccount size={18} />
        ) : (
            <MentatIcon />
        );
    const sourceName = props.message.source === "user" ? "You" : "Mentat";

    // Assemble file edit blocks
    const messagesPieces: JSX.Element[] = [];
    let curBlock: MessageContent[] = [];
    for (const contentPiece of props.message.content) {
        if (contentPiece.filepath) {
            if (
                curBlock.length === 0 ||
                contentPiece.filepath === curBlock[0].filepath
            ) {
                curBlock.push(contentPiece);
            } else {
                messagesPieces.push(renderFileBlock(curBlock));
                curBlock = [];
            }
        } else {
            if (curBlock.length !== 0) {
                messagesPieces.push(renderFileBlock(curBlock));
                curBlock = [];
            }
            messagesPieces.push(
                renderContentPiece(contentPiece, messagesPieces.length)
            );
        }
    }
    if (curBlock.length !== 0) {
        messagesPieces.push(renderFileBlock(curBlock));
    }

    const messageContent = (
        <pre className="whitespace-pre-wrap">
            {messagesPieces.map((messagePiece, index) => (
                <React.Fragment key={index}>{messagePiece}</React.Fragment>
            ))}
        </pre>
    );

    // TODO: Should we put a warning or error box around specific styles?
    /*
    chatMessageContent = (
        <div className="bg-red-500 p-2 rounded-md flex gap-2 text-white">
            <WarningIcon />
            {content}
        </div>
    );
    */

    return (
        <div className="flex flex-col gap-2 p-2 border-t border-[var(--vscode-panel-border)]">
            <div className="flex gap-2 pt-2">
                {sourceIcon}
                <p className="font-bold">{sourceName}</p>
            </div>
            {messageContent}
        </div>
    );
}
