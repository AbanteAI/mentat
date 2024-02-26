import { KeyboardEvent, useEffect, useRef, useState } from "react";
import { VscSend } from "react-icons/vsc";

type Props = {
    onUserInput: (input: string) => void;
    inputRequestId: string | undefined;
};

export default function ChatInput(props: Props) {
    const textAreaRef = useRef<HTMLTextAreaElement>(null);
    const [textAreaValue, setTextAreaValue] = useState<string>("");
    const [submitDisabled, setSubmitDisabled] = useState(true);

    useEffect(() => {
        setSubmitDisabled(
            textAreaValue === "" || props.inputRequestId === undefined
        );

        if (textAreaRef.current) {
            textAreaRef.current.style.height = "auto";
            textAreaRef.current.style.height = `${textAreaRef.current.scrollHeight}px`;
        }
    }, [textAreaValue]);

    function handleChange(event: React.ChangeEvent<HTMLTextAreaElement>) {
        setTextAreaValue(event.target.value);
    }

    function handleSubmit() {
        if (submitDisabled) {
            return;
        }
        props.onUserInput(textAreaValue);

        setTextAreaValue("");
    }

    function handleKeyPress(event: KeyboardEvent<HTMLTextAreaElement>) {
        if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            handleSubmit();
        }
    }

    return (
        <div className="pb-4">
            <div className="relative flex bg-[var(--vscode-input-background)] rounded-md">
                <textarea
                    ref={textAreaRef}
                    className="flex-1 focus:outline-[var(--vscode-focusBorder)] rounded-md resize-none bg-[var(--vscode-input-background)] p-2"
                    placeholder="What can I do for you?"
                    style={{
                        height: "auto",
                        overflow: "hidden",
                        scrollbarWidth: "none",
                    }}
                    rows={1}
                    value={textAreaValue}
                    onKeyDown={handleKeyPress}
                    onChange={handleChange}
                />
                <button
                    className={`${
                        !submitDisabled &&
                        "hover:bg-[var(--vscode-button-secondaryHoverBackground)]"
                    } w-6 h-6 flex justify-center items-center rounded-md fixed bottom-0 right-0 mr-6 mb-[22px]`}
                    onClick={handleSubmit}
                    disabled={submitDisabled}
                >
                    <VscSend
                        color={
                            submitDisabled
                                ? "var(--vscode-disabledForeground)"
                                : "var(--vscode-button-foreground)"
                        }
                        size={18}
                    />
                </button>
            </div>
        </div>
    );
}
