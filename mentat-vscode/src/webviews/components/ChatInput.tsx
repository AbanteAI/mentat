import { KeyboardEvent, useEffect, useRef, useState } from "react";
import { VscError, VscSend } from "react-icons/vsc";

type Props = {
    onUserInput: (input: string) => void;
    inputRequestId: string | null;
    sessionActive: boolean;
    textAreaValue: string;
    setTextAreaValue: (input: string) => void;
    cancelEnabled: boolean;
    onCancel: () => void;
};

export default function ChatInput(props: Props) {
    const textAreaRef = useRef<HTMLTextAreaElement>(null);
    const [submitDisabled, setSubmitDisabled] = useState(true);

    useEffect(() => {
        setSubmitDisabled(
            props.textAreaValue === "" ||
                props.inputRequestId === null ||
                !props.sessionActive
        );

        if (textAreaRef.current) {
            textAreaRef.current.style.height = "auto";
            textAreaRef.current.style.height = `${textAreaRef.current.scrollHeight}px`;
        }
    }, [props.textAreaValue]);

    function handleChange(event: React.ChangeEvent<HTMLTextAreaElement>) {
        props.setTextAreaValue(event.target.value);
    }

    function handleSubmit() {
        if (submitDisabled) {
            return;
        }
        props.onUserInput(props.textAreaValue);
        props.setTextAreaValue("");
    }

    function handleKeyPress(event: KeyboardEvent<HTMLTextAreaElement>) {
        if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            handleSubmit();
        }
    }

    return (
        <div className="flex flex-row items-center pb-4 relative">
            <div className="relative flex-1 bg-[var(--vscode-input-background)] rounded-md">
                <textarea
                    ref={textAreaRef}
                    className="w-full h-full block flex-1 focus:outline-[var(--vscode-focusBorder)] rounded-md resize-none bg-[var(--vscode-input-background)] p-2"
                    placeholder="What can I do for you?"
                    style={{
                        overflow: "hidden",
                        scrollbarWidth: "none",
                    }}
                    rows={1}
                    value={props.textAreaValue}
                    onKeyDown={handleKeyPress}
                    onChange={handleChange}
                    disabled={!props.sessionActive}
                />
            </div>
            <button
                className={`${
                    !submitDisabled &&
                    "hover:bg-[var(--vscode-button-secondaryHoverBackground)]"
                } w-6 h-6 flex justify-center items-center rounded-md absolute bottom-[22px] right-10`}
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
            <button
                className={`${
                    props.cancelEnabled &&
                    "hover:bg-[var(--vscode-button-secondaryHoverBackground)]"
                } w-6 h-6 flex justify-center items-center rounded-md ml-2`}
                onClick={props.onCancel}
                disabled={!props.cancelEnabled}
            >
                <VscError
                    color={
                        props.cancelEnabled
                            ? "var(--vscode-errorForeground)"
                            : "var(--vscode-disabledForeground)"
                    }
                    size={22}
                />
            </button>
        </div>
    );
}
