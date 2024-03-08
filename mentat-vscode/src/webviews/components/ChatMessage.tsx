import { VscAccount } from "react-icons/vsc";
import { Message } from "types";
import MentatIcon from "./MentatIcon";

type Props = {
    message: Message;
};

const light_theme: { [id: string]: string } = {
    prompt: "gray",
    code: "blue",
    info: "cyan",
    failure: "dark_red",
    success: "green",
    input: "bright_blue",
    error: "red",
    warning: "yellow",
};
const dark_theme: { [id: string]: string } = {
    prompt: "white",
    code: "blue",
    info: "cyan",
    failure: "bright_red",
    success: "green",
    input: "bright_blue",
    error: "red",
    warning: "yellow",
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
        <pre className="whitespace-pre-wrap">
            {props.message.content.map((contentPiece, index) => (
                <span
                    style={{
                        color:
                            contentPiece.color ||
                            (contentPiece.style &&
                                dark_theme[contentPiece.style]),
                    }}
                    key={index}
                >
                    {contentPiece.text}
                </span>
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
