import { Card } from "@/components/ui/card";
import IconComponent from "@/components/common/genericIconComponent";
import { MessageBubbleProps, FileAttachment, BlockContent } from "../types";
import { Badge } from "@/components/ui/badge";
import React, { useState } from "react";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";

export function MessageBubble({ message, isUser }: MessageBubbleProps) {
  // Parse files if they're a string
  const files = typeof message.files === 'string'
    ? (message.files === '[]' || message.files === '' ? [] : JSON.parse(message.files))
    : message.files || [];

  const [isOpen, setIsOpen] = useState(false);

  // Check if message has Agent Steps content block
  const hasAgentSteps = message.content_blocks &&
    message.content_blocks.length > 0 &&
    message.content_blocks.some(block => block.title === "Agent Steps");

  return (
    <div
      className={`flex ${isUser ? "justify-end" : "justify-start"
        }`}
    >

      <Card
        className={`max-w-[80%] p-4 ${isUser
            ? "bg-primary text-primary-foreground"
            : "bg-muted"
          }`}
      >
        <div className="flex items-center gap-2 mb-1">
          {message.properties?.icon && (
            <IconComponent name={message.properties.icon} className="h-4 w-4 text-primary" />
          )}
          <span className="font-semibold">{message.sender_name}</span>
          {message.properties?.source?.display_name && (
            <Badge variant="outline" className="text-xs">
              {message.properties.source.display_name}
            </Badge>
          )}
          {/* <span className="text-xs text-muted-foreground">
            {new Date(message.timestamp).toLocaleTimeString()}
          </span> */}
        </div>

        {/* Display agent steps in a collapsible section */}
        {hasAgentSteps && (
          <Collapsible
            open={isOpen}
            onOpenChange={setIsOpen}
            className="mt-3 border rounded-md overflow-hidden"
          >
            <CollapsibleTrigger className="flex items-center justify-between w-full p-2 bg-secondary/30 hover:bg-secondary/50 transition-colors">
              <div className="flex items-center gap-2">
                <IconComponent name="Activity" className="h-4 w-4 text-primary" />
                <span className="font-medium text-sm">View Agent Steps</span>
              </div>
              <IconComponent name={isOpen ? "ChevronUp" : "ChevronDown"} className="h-4 w-4" />
            </CollapsibleTrigger>
            <CollapsibleContent>
              <div className="p-3 bg-background/50 text-sm">
                {message.content_blocks
                  .filter(block => block.title === "Agent Steps")
                  .map((block, i) => (
                    <div key={i} className="space-y-3">
                      {block.contents.map((content, j) => (
                        <ContentItem key={j} content={content} />
                      ))}
                    </div>
                  ))}
              </div>
            </CollapsibleContent>
          </Collapsible>
        )}


        <p className="whitespace-pre-wrap break-words">{message.text}</p>

        {/* Display file attachments */}
        {files && files.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-2">
            {files.map((file: FileAttachment | string, i: number) => {
              // Handle both string paths and FileAttachment objects
              const fileObj = typeof file === 'string'
                ? { path: file, name: file.split('/').pop() || file, type: getFileType(file) }
                : file;

              return (
                <Badge
                  key={i}
                  variant="outline"
                  className="flex items-center gap-1 p-1 pl-2"
                >
                  <FileIcon type={fileObj.type} />
                  <a
                    href={fileObj.path}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="max-w-[150px] truncate hover:underline"
                  >
                    {fileObj.name}
                  </a>
                </Badge>
              );
            })}
          </div>
        )}


      </Card>
    </div>
  );
}

// Component to render different types of content blocks
function ContentItem({ content }: { content: BlockContent }) {
  const { type, header, text } = content;

  // Calculate duration in a human-readable format
  const formatDuration = (ms: number) => {
    if (ms < 1000) return `${ms}ms`;
    const seconds = ms / 1000;
    return `${seconds.toFixed(1)}s`;
  };

  return (
    <div className="border-l-2 border-primary/20 pl-3 py-1">
      <div className="flex items-center justify-between mb-1">
        <div className="flex items-center gap-1.5 text-xs font-medium">
          <IconComponent name={header.icon} className="h-3.5 w-3.5 text-primary" />
          <span>{header.title}</span>
        </div>
        <Badge variant="outline" className="text-xs px-1.5 py-0.5 h-5">
          {formatDuration(content.duration)}
        </Badge>
      </div>

      {type === "text" && (
        <div className="text-sm whitespace-pre-wrap pl-1 mt-1">
          {text}
        </div>
      )}

      {type === "tool_use" && (
        <div className="text-sm pl-1 mt-1">
          <div className="font-medium text-xs text-muted-foreground mb-1">Tool: {content.name}</div>
          {content.tool_input && (
            <div className="bg-muted/50 p-2 rounded-sm mb-2 overflow-x-auto">
              <pre className="text-xs">{JSON.stringify(content.tool_input, null, 2)}</pre>
            </div>
          )}
          {content.output && (
            <div>
              <div className="font-medium text-xs text-muted-foreground mb-1">Output:</div>
              <div className="bg-muted/50 p-2 rounded-sm overflow-x-auto">
                <pre className="text-xs">{JSON.stringify(content.output, null, 2)}</pre>
              </div>
            </div>
          )}
          {content.error && (
            <div className="text-destructive">
              <div className="font-medium text-xs mb-1">Error:</div>
              <div className="bg-destructive/10 p-2 rounded-sm overflow-x-auto">
                <pre className="text-xs">{content.error}</pre>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// Helper component to show appropriate icon based on file type
function FileIcon({ type }: { type: string }) {
  let iconName = "File";

  if (type.includes("image")) {
    iconName = "Image";
  } else if (type.includes("pdf")) {
    iconName = "FileText";
  } else if (type.includes("video")) {
    iconName = "Video";
  } else if (type.includes("audio")) {
    iconName = "Music";
  } else if (type.includes("zip") || type.includes("rar") || type.includes("tar")) {
    iconName = "Archive";
  }

  return <IconComponent name={iconName} className="h-3 w-3" />;
}

// Helper function to determine file type from path
function getFileType(path: string): string {
  const extension = path.split('.').pop()?.toLowerCase() || '';

  const typeMap: Record<string, string> = {
    'jpg': 'image/jpeg',
    'jpeg': 'image/jpeg',
    'png': 'image/png',
    'gif': 'image/gif',
    'pdf': 'application/pdf',
    'doc': 'application/msword',
    'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    'xls': 'application/vnd.ms-excel',
    'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    'ppt': 'application/vnd.ms-powerpoint',
    'pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    'mp3': 'audio/mpeg',
    'mp4': 'video/mp4',
    'zip': 'application/zip',
    'rar': 'application/x-rar-compressed',
    'tar': 'application/x-tar',
    'txt': 'text/plain',
    'csv': 'text/csv',
    'json': 'application/json',
  };

  return typeMap[extension] || 'application/octet-stream';
} 