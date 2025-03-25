import React, { useState } from "react";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import IconComponent from "@/components/common/genericIconComponent";
import { cn } from "@/utils/utils";
import { Message, BlockContent } from "../../types";

interface WorkflowSectionProps {
  title: string;
  icon: string;
  children: React.ReactNode;
  defaultOpen?: boolean;
  titleDescription?: string;
  duration?: number;
  variant?: "primary" | "secondary";
}

export function WorkflowSection({ 
  title, 
  icon, 
  children, 
  defaultOpen = false,
  titleDescription,
  duration,
  variant = "primary"
}: WorkflowSectionProps) {
  const [isOpen, setIsOpen] = useState(defaultOpen);

  // Format duration if provided
  const formatDuration = (ms: number) => {
    if (ms < 1000) return `${ms}ms`;
    const seconds = ms / 1000;
    return `${seconds.toFixed(1)}s`;
  };

  return (
    <Accordion
      type="single"
      collapsible
      defaultValue={defaultOpen ? "item-1" : undefined}
      className="w-full border rounded-md mb-3 overflow-hidden"
    >
      <AccordionItem value="item-1" className="border-0">
        <AccordionTrigger 
          className={cn(
            "p-3 hover:no-underline",
            variant === "primary" 
              ? "bg-background hover:bg-muted/50" 
              : "bg-muted/30 hover:bg-muted/50"
          )}
          onClick={() => setIsOpen(!isOpen)}
        >
          <div className="flex items-center gap-2 text-left">
            <IconComponent name="bot" className="h-5 w-5 text-primary" />
            <div className="flex flex-col">
              <span className="font-semibold text-sm">{title}</span>
              {titleDescription && (
                <span className="text-xs text-muted-foreground">{titleDescription}</span>
              )}
            </div>
          </div>
          {duration && (
            <span className="text-xs text-muted-foreground">
              {formatDuration(duration)}
            </span>
          )}
        </AccordionTrigger>
        <AccordionContent className="p-0 border-t">
          <div className="p-3 bg-background">{children}</div>
        </AccordionContent>
      </AccordionItem>
    </Accordion>
  );
}

// Component for rendering JSON or object data
export function TechnicalDetails({ 
  data, 
  title = "Technical Details",
  icon = "Code"
}: { 
  data: any; 
  title?: string;
  icon?: string;
}) {
  return (
    <WorkflowSection title={title} icon={icon} variant="secondary">
      <div className="bg-muted/50 p-2 rounded-sm overflow-x-auto">
        <pre className="text-xs whitespace-pre-wrap">{JSON.stringify(data, null, 2)}</pre>
      </div>
    </WorkflowSection>
  );
}

// Component for tool execution details
export function ToolExecutionItem({ content }: { content: BlockContent }) {
  return (
    <div className="mb-4">
      <div className="flex items-center gap-2 mb-2">
        <IconComponent name={content.header.icon} className="h-4 w-4 text-primary" />
        <span className="font-medium text-sm">{content.header.title}</span>
      </div>
      
      {content.type === "tool_use" && (
        <div className="pl-6 space-y-3">
          <div className="text-xs text-muted-foreground mb-1">Tool: {content.name}</div>
          
          {content.tool_input && (
            <TechnicalDetails data={content.tool_input} title="Input" icon="ArrowDownCircle" />
          )}
          
          {content.output && (
            <TechnicalDetails data={content.output} title="Output" icon="ArrowUpCircle" />
          )}
          
          {content.error && (
            <WorkflowSection title="Error" icon="AlertCircle" variant="secondary">
              <div className="bg-destructive/10 p-2 rounded-sm overflow-x-auto">
                <pre className="text-xs text-destructive">{content.error}</pre>
              </div>
            </WorkflowSection>
          )}
        </div>
      )}
      
      {content.type === "text" && (
        <div className="pl-6 text-sm">
          {content.text}
        </div>
      )}
    </div>
  );
} 