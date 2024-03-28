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
                "basis-1 py-1 px-3 rounded-sm w-fit whitespace-nowrap border-solid border-2 border-[var(--vscode-focusBorder)] " +
                (props.className ? props.className : "")
            }
            onClick={props.onClick}
        >
            {props.children}
        </button>
    );
}
