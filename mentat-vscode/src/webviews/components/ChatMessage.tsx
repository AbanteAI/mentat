import { VscAccount } from "react-icons/vsc";
import { Message } from "types";
import MentatIcon from "./MentatIcon";

type Props = {
    message: Message;
};

// TODO: Once everything is working, make sure to memoize!!!
export default function ChatMessage(props: Props) {
    const sourceIcon =
        props.message.source === "user" ? (
            <VscAccount size={18} />
        ) : (
            <MentatIcon />
        );
    const sourceName = props.message.source === "user" ? "You" : "Mentat";

    // Using index as key should be fine since we never insert, delete, or re-order chat messages
    const messageContent = (
        <pre>
            {props.message.content.map((contentPiece, index) => (
                <span className={contentPiece.color} key={index}>
                    {contentPiece.text}
                </span>
            ))}
        </pre>
    );

    /*
    chatMessageContent = (
        <div className="bg-red-500 p-2 rounded-md flex gap-2 text-white">
            <WarningIcon />
            {content}
        </div>
    );

    chatMessageContent = (
        <div className="bg-[var(--vscode-textCodeBlock-background)]">
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
