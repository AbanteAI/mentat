import { VscAccount } from "react-icons/vsc";
import { FileEdit, Message, MessageContent } from "types";
import MentatIcon from "./MentatIcon";
import React from "react";
import PillButton from "./PillButton";

// TODO: Change the colors to vscode theme colors
const light_theme: { [id: string]: string } = {
    prompt: "gray",
    code: "blue",
    info: "lightblue",
    failure: "darkred",
    success: "green",
    input: "lightblue",
    error: "red",
    warning: "yellow",
};
const dark_theme: { [id: string]: string } = {
    prompt: "white",
    code: "blue",
    info: "lightblue",
    failure: "red",
    success: "green",
    input: "lightblue",
    error: "darkred",
    warning: "yellow",
};

/**
 * Renders a small piece of content with a single style/color/filepath
 */
function ContentPiece({ contentPiece }: { contentPiece: MessageContent }) {
    return (
        <span
            style={{
                color:
                    contentPiece.color?.replace("bright_", "light") ||
                    (contentPiece.style && dark_theme[contentPiece.style]),
            }}
            className={
                contentPiece.delimiter ? "border-solid border-b block my-2" : ""
            }
        >
            {contentPiece.text}
        </span>
    );
}

/**
 * Renders an edit fileblock
 */
function FileBlock({
    contentPieces,
    activeEdits,
    onAccept,
    onDecline,
    onPreview,
}: {
    contentPieces: MessageContent[];
    activeEdits: FileEdit[];
    onAccept: (fileEdit: FileEdit) => void;
    onDecline: (fileEdit: FileEdit) => void;
    onPreview: (fileEdit: FileEdit) => void;
}) {
    const filePath = contentPieces.at(0)?.filepath;
    if (filePath === undefined) {
        return;
    }
    const filePathDisplay = contentPieces.at(0)?.filepath_display ?? filePath;

    const activeEdit = activeEdits.find(
        (fileEdit) => fileEdit.file_path === filePath
    );

    var filePathColor;
    switch (filePathDisplay[1]) {
        case "creation": {
            filePathColor = "lightgreen";
            break;
        }
        case "deletion": {
            filePathColor = "red";
            break;
        }
        case "rename": {
            filePathColor = "yellow";
            break;
        }
        default: {
            filePathColor = "lightblue";
            break;
        }
    }
    var acceptText = "Accept";
    if (activeEdit) {
        switch (activeEdit.type) {
            case "creation": {
                acceptText = "Create File";
                break;
            }
            case "deletion": {
                acceptText = "Delete File";
                break;
            }
        }
    }

    return (
        // hover:bg-[var(--vscode-inputOption-hoverBackground)] hover:scale-[1.01] transition-all duration-500 ease-out
        <fieldset className="border-solid rounded-md border min-w-[30%] max-w-[80%] w-fit p-1 bg-[var(--vscode-input-background)]">
            <legend
                style={{
                    color: filePathColor,
                }}
            >
                {filePathDisplay[0]}
            </legend>
            {contentPieces.map((contentPiece, index) => (
                // Index as key should be fine here since we never insert reorder or delete elements
                <ContentPiece
                    contentPiece={contentPiece}
                    key={index}
                ></ContentPiece>
            ))}
            {
                // TODO: See if a checkmark, x, and pencil logo would look good on these buttons
                activeEdit && (
                    <>
                        <span className="border-solid border-b block my-2"></span>
                        <div className="flex flex-row flex-wrap gap-3 ml-1 mb-1 mr-auto">
                            <PillButton
                                className="bg-[var(--vscode-button-background)] hover:bg-[var(--vscode-button-hoverBackground)]"
                                onClick={() => onAccept(activeEdit)}
                            >
                                {acceptText}
                            </PillButton>
                            <PillButton
                                className="bg-[var(--vscode-button-background)] hover:bg-[var(--vscode-button-hoverBackground)]"
                                onClick={() => onDecline(activeEdit)}
                            >
                                Decline
                            </PillButton>
                            {activeEdit.type === "edit" && (
                                <PillButton
                                    className="bg-[var(--vscode-button-secondaryBackground)] hover:bg-[var(--vscode-button-secondaryHoverBackground)]"
                                    onClick={() => onPreview(activeEdit)}
                                >
                                    Review
                                </PillButton>
                            )}
                        </div>
                    </>
                )
            }
        </fieldset>
    );
}

type Props = {
    message: Message;
    activeEdits: FileEdit[];
    onAccept: (fileEdit: FileEdit) => void;
    onDecline: (fileEdit: FileEdit) => void;
    onPreview: (fileEdit: FileEdit) => void;
};

// TODO: Memoize this component if we need the performace increase. Will need to wrap prop functions in useCallback.
/**
 * Renders an entire message from either the user or mentat
 */
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
                messagesPieces.push(
                    <FileBlock
                        contentPieces={curBlock}
                        activeEdits={props.activeEdits}
                        onAccept={props.onAccept}
                        onDecline={props.onDecline}
                        onPreview={props.onPreview}
                    ></FileBlock>
                );
                curBlock = [contentPiece];
            }
        } else {
            if (curBlock.length !== 0) {
                messagesPieces.push(
                    <FileBlock
                        contentPieces={curBlock}
                        activeEdits={props.activeEdits}
                        onAccept={props.onAccept}
                        onDecline={props.onDecline}
                        onPreview={props.onPreview}
                    ></FileBlock>
                );
                curBlock = [];
            }
            messagesPieces.push(
                <ContentPiece contentPiece={contentPiece}></ContentPiece>
            );
        }
    }
    if (curBlock.length !== 0) {
        messagesPieces.push(
            <FileBlock
                contentPieces={curBlock}
                activeEdits={props.activeEdits}
                onAccept={props.onAccept}
                onDecline={props.onDecline}
                onPreview={props.onPreview}
            ></FileBlock>
        );
    }

    const messageContent = (
        <pre
            className="whitespace-pre-wrap"
            style={{
                fontFamily: "var(--vscode-editor-font-family), monospace",
            }}
        >
            {messagesPieces.map((messagePiece, index) => (
                <React.Fragment key={index}>{messagePiece}</React.Fragment>
            ))}
        </pre>
    );

    return (
        <div className="flex flex-col gap-2 p-1 border-t border-[var(--vscode-panel-border)]">
            <div className="flex gap-2 pt-2">
                {sourceIcon}
                <p className="font-bold">{sourceName}</p>
            </div>
            {messageContent}
            {props.activeEdits.length > 0 && (
                <>
                    <div className="flex flex-row flex-wrap gap-3 ml-1 mb-1 mr-auto">
                        <PillButton
                            className="bg-[var(--vscode-button-background)] hover:bg-[var(--vscode-button-hoverBackground)]"
                            onClick={() =>
                                props.activeEdits.map(props.onAccept)
                            }
                        >
                            Accept All
                        </PillButton>
                        <PillButton
                            className="bg-[var(--vscode-button-background)] hover:bg-[var(--vscode-button-hoverBackground)]"
                            onClick={() =>
                                props.activeEdits.map(props.onDecline)
                            }
                        >
                            Decline All
                        </PillButton>
                    </div>
                </>
            )}
        </div>
    );
}
