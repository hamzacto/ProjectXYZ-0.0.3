import { useState, KeyboardEvent, useRef, ChangeEvent } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import IconComponent from "@/components/common/genericIconComponent";
import { ChatInputProps } from "../types";
import { Badge } from "@/components/ui/badge";

export function ChatInput({ onSendMessage, disabled, loading, placeholder }: ChatInputProps) {
  const [message, setMessage] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // const handleSend = () => {
  //   if ((!message.trim() && files.length === 0) || disabled) return;
    
  //   // Use the new interface format matching IOModal
  //   onSendMessage({
  //     text: message,
  //     repeat: 1,
  //     files: files
  //   });
    
  //   setMessage("");
  //   setFiles([]);
  // };

  const send = () => {
    onSendMessage({
      repeat: 1
    });
    setFiles([]);
  };


  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  };

  const handleFileChange = (e: ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      setFiles(Array.from(e.target.files));
    }
  };

  const handleRemoveFile = (index: number) => {
    setFiles(files.filter((_, i) => i !== index));
  };

  return (
    <div className="flex flex-col gap-2">
      {files.length > 0 && (
        <div className="flex flex-wrap gap-2 p-2 border rounded-md">
          {files.map((file, index) => (
            <Badge key={index} variant="secondary" className="flex items-center gap-1">
              <span className="max-w-[150px] truncate">{file.name}</span>
              <button
                type="button"
                onClick={() => handleRemoveFile(index)}
                className="text-muted-foreground hover:text-foreground"
              >
                <IconComponent name="X" className="h-3 w-3" />
              </button>
            </Badge>
          ))}
        </div>
      )}
      <div className="flex gap-2">
        <Input
          placeholder={placeholder || "Type a message..."}
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={disabled || loading}
          className="flex-1"
        />
        <input
          type="file"
          multiple
          ref={fileInputRef}
          onChange={handleFileChange}
          className="hidden"
          disabled={disabled || loading}
        />
        <Button
          type="button"
          variant="outline"
          size="icon"
          onClick={() => fileInputRef.current?.click()}
          disabled={disabled || loading}
          title="Attach files"
        >
          <IconComponent name="PaperClip" className="h-4 w-4" />
        </Button>
        <Button
          onClick={() => {
            onSendMessage({
              repeat: 1,
            });
          }}
          disabled={disabled || loading || (!message.trim() && files.length === 0)}
        >
          {loading ? (
            <IconComponent name="Loader2" className="h-4 w-4 animate-spin" />
          ) : (
            <IconComponent name="Send" className="h-4 w-4" />
          )}
        </Button>
      </div>
    </div>
  );
} 