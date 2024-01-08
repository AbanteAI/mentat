import {
  Dispatch,
  KeyboardEvent,
  SetStateAction,
  useEffect,
  useRef,
  useState,
} from "react"
import { VscSend } from "react-icons/vsc"
import { vscode } from "webviews/utils/vscode"

import { ChatMessage, LanguageServerMessage } from "../../types"

type Props = {
  chatMessages: ChatMessage[]
  setChatMessages: Dispatch<SetStateAction<ChatMessage[]>>
  inputRequestId: string | null
}

export default function ChatInput(props: Props) {
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const [textareaValue, setTextareaValue] = useState<string>("")
  const [textareaHeight, setTextareaHeight] = useState<number | string>("auto")
  const [submitDisabled, setSubmitDisabled] = useState(true)

  useEffect(() => {
    if (textareaValue === "") {
      setSubmitDisabled(true)
    } else {
      setSubmitDisabled(false)
    }

    if (textareaRef.current) {
      textareaRef.current.style.height = "auto"
      textareaRef.current.style.height = `${textareaRef.current.scrollHeight}px`
    }
  }, [textareaValue])

  function handleChange(event: React.ChangeEvent<HTMLTextAreaElement>) {
    setTextareaValue(event.target.value)
  }

  function handleSubmit() {
    if (submitDisabled || props.inputRequestId === null) {
      return
    }

    props.setChatMessages((prevMessages) => {
      const newChatMessage: ChatMessage = {
        id:
          prevMessages.length === 0
            ? 0
            : prevMessages[prevMessages.length - 1].id + 1,
        content: textareaValue,
        source: "client",
      }
      return [...prevMessages, newChatMessage]
    })

    const message: LanguageServerMessage = {
      type: "request",
      method: "mentat/clientMessage",
      data: textareaValue,
    }
    vscode.postMessage(message)

    setTextareaValue("")
  }

  function handleKeyPress(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault()
      handleSubmit()
    }
  }

  return (
    <div className="pb-4">
      <div className="relative flex bg-[var(--vscode-input-background)] rounded-md">
        <textarea
          ref={textareaRef}
          className="flex-1 focus:outline-[var(--vscode-focusBorder)] rounded-md resize-none bg-[var(--vscode-input-background)] p-2"
          placeholder="What can I do for you?"
          style={{
            height: textareaHeight,
            overflow: "hidden",
            scrollbarWidth: "none",
          }}
          rows={1}
          value={textareaValue}
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
  )
}
