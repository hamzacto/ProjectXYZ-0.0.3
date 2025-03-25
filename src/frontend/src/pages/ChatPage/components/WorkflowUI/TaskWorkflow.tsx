import React, { useMemo, useRef, useEffect, useState } from "react";
import type { Message } from "@/types/messages";
import { FileAttachment } from "../../types";
import IconComponent from "@/components/common/genericIconComponent";
import { WorkflowFileAttachment } from "./WorkflowFileAttachment";
import { Card } from "@/components/ui/card";
import { cn } from "@/utils/utils";
import "./customStyles.css";
import { MarkdownField } from "@/modals/IOModal/components/chatView/chatMessage/components/edit-message";
import { ContentBlockDisplay } from "@/components/core/chatComponents/ContentBlockDisplay";
import { ContentBlock } from "@/types/chat";
import { UserMessage } from "./UserMessage";

interface TaskWorkflowProps {
    messages: Message[];
    query?: string;
}

// Helper function to safely process file objects
const processFile = (file: FileAttachment | string): { path: string; name: string; type: string } => {
    if (typeof file === 'string') {
        const name = file.split('/').pop() || file;
        const type = file.split('.').pop() || 'unknown';
        return { path: file, name, type };
    }
    return file;
};

export function TaskWorkflow({ messages, query }: TaskWorkflowProps) {
    const messagesEndRef = useRef<HTMLDivElement>(null);
    const containerRef = useRef<HTMLDivElement>(null);
    const prevMessagesLengthRef = useRef<number>(0);
    const [latestMessageId, setLatestMessageId] = useState<string | null>(null);
    
    // Auto-scroll to bottom when new messages arrive
    useEffect(() => {
        if (messages.length > prevMessagesLengthRef.current) {
            // Set the latest message for animation
            if (messages.length > 0) {
                const sortedMsgs = [...messages].sort((a, b) => 
                    new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
                );
                setLatestMessageId(sortedMsgs[0].id);
            }
            
            // Smooth scroll to bottom
            setTimeout(() => {
                messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
            }, 100);
            
            // Reset animation class after animation completes
            setTimeout(() => {
                setLatestMessageId(null);
            }, 800);
        }
        prevMessagesLengthRef.current = messages.length;
    }, [messages]);
    
    if (messages.length === 0) {
        return (
            <div className="flex h-full items-center justify-center">
                <p className="text-muted-foreground">
                    No messages yet. Start a conversation!
                </p>
            </div>
        );
    }

    const sortedMessages = useMemo(() => {
        return [...messages].sort((a, b) => {
            return new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime();
        });
    }, [messages]);

    // Determine if we need extra spacing at the top to prevent too much scrolling with few messages
    const extraSpacing = messages.length <= 2 ? 'mt-auto' : '';

    return (
        <div 
            ref={containerRef}
            className={`chat-container space-y-0 max-w-3xl mx-auto overflow-y-auto no-scrollbar flex flex-col ${extraSpacing}`}
            style={{
                minHeight: '100%',
            }}
        >
            {sortedMessages.map((message, index) => {
                const isUser = message.sender === "User";
                const isLatest = message.id === latestMessageId;
                const messageClass = isLatest ? "message-enter" : "";

                if (isUser) {
                    return (
                        <div key={`msg-${message.id}`} className={messageClass}>
                            <UserMessage message={message} />
                        </div>
                    );
                } else {
                    return (
                        <div key={`msg-${message.id}`} className={`w-auto max-w-[768px] py-4 word-break-break-word ${messageClass}`}>
                            <div className="group relative flex w-full gap-4 rounded-md p-2 hover:bg-muted/50 transition-colors duration-200">
                                <div className={cn(
                                    "relative flex h-[32px] w-[32px] items-center justify-center overflow-hidden rounded-md text-2xl",
                                    "bg-muted"
                                )}>
                                    <div className="flex h-[18px] w-[18px] items-center justify-center">
                                        {message.properties?.icon && (
                                            <IconComponent name={message.properties.icon} className="h-4 w-4 text-primary" />
                                        )}
                                    </div>
                                </div>
                                <div className="flex w-[94%] flex-col">
                                    <div>
                                        <div className={cn(
                                            "flex max-w-full items-baseline gap-3 truncate pb-2 text-[14px] font-semibold"
                                        )}>
                                            {message.sender_name}
                                            {message.properties?.source?.display_name && (
                                                <div className="text-[13px] font-normal text-muted-foreground">
                                                    {message.properties.source.display_name}
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                    {message.content_blocks && message.content_blocks.length > 0 && (
                                        <ContentBlockDisplay
                                            contentBlocks={message.content_blocks}
                                            isLoading={false}
                                            state={message.properties?.state}
                                            chatId={message.id}
                                        />
                                    )}
                                    <div className="form-modal-chat-text-position flex-grow">
                                        <div className="form-modal-chat-text">
                                            <div className="flex w-full flex-col">
                                                <div className="flex w-full flex-col dark:text-white">
                                                    <div className="flex w-full flex-col">
                                                        <div className="w-full">
                                                            <MarkdownField
                                                                chat={message}
                                                                isEmpty={!message.text}
                                                                chatMessage={message.text || ""}
                                                                editedFlag={null}
                                                            />
                                                        </div>
                                                    </div>
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                    {message.files && (
                                        <div className="my-2 flex flex-col gap-5">
                                            <WorkflowFileAttachment files={
                                                Array.isArray(message.files) ? message.files :
                                                    (message.files === '[]' || message.files === '') ? [] :
                                                        JSON.parse(message.files)
                                            } />
                                        </div>
                                    )}
                                </div>
                            </div>
                        </div>
                    );
                }
            })}
            <div ref={messagesEndRef} />
        </div>
    );
} 