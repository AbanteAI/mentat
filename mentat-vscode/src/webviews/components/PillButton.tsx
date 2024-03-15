import React from "react";

type Props = {
    children: React.ReactNode;
    className?: string;
    onClick?: () => void;
};

export default function PillButton(props: Props) {
    return (
        <button
            className={
                "basis-1 py-1 px-3 rounded-full w-fit whitespace-nowrap hover:scale-[1.12] transition-all duration-500 ease-out border-solid border-2 border-[var(--vscode-focusBorder)] " +
                (props.className ? props.className : "")
            }
            onClick={props.onClick}
        >
            {props.children}
        </button>
    );
}
