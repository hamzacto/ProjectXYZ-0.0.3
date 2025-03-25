import React from "react";
import type { Message } from "@/types/messages";
import { Card } from "@/components/ui/card";
import { useDarkStore } from "@/stores/darkStore";

interface UserMessageProps {
    message: Message;
}

export function UserMessage({ message }: UserMessageProps) {
    if (!message) return null;
    
    const dark = useDarkStore((state) => state.dark);
    const backgroundColor = dark ? "#303030" : "#f3f3f3";
    const textColor = dark ? "white" : "black";
    
    return (
        <div className="w-auto max-w-[768px] py-4 word-break-break-word">
            <div className="flex justify-end">
                <Card className="max-w-[80%] py-3 px-4 message-transition rounded-3xl shadow-none border-0 transition-colors duration-200" style={{ backgroundColor, color: textColor }}>
                    <span className="whitespace-pre-wrap break-words text-[14px]">
                        {message.text}
                    </span>
                </Card>
            </div>
        </div>
    );
} 