import React from "react";
import { Badge } from "@/components/ui/badge";
import IconComponent from "@/components/common/genericIconComponent";
import { BlockContent } from "../../types";
import { MarkdownRenderer } from "./MarkdownRenderer";

interface AgentStepsTimelineProps {
  contents: BlockContent[];
}

export function AgentStepsTimeline({ contents }: AgentStepsTimelineProps) {
  return (
    <div className="space-y-4 bg-background/50 rounded-md">
      {contents.map((content, index) => (
        <StepItem key={index} content={content} />
      ))}
    </div>
  );
}

function StepItem({ content }: { content: BlockContent }) {
  return (
    <div className="border-l-2 border-primary/20 pl-4 py-2 hover:bg-muted/30 transition-colors rounded-r-md">
      <div className="flex items-center justify-between mb-1.5">
        <div className="flex items-center gap-2">
          <IconComponent 
            name={content.header.icon || "Activity"} 
            className="h-4 w-4 text-primary" 
          />
          {content.header.title && content.header.title.includes("Executed **") ? (
            <div className="font-medium text-sm">
              <MarkdownRenderer content={content.header.title} className="m-0 p-0 inline" />
            </div>
          ) : (
            <span className="font-medium text-sm">{content.header.title}</span>
          )}
        </div>
        <Badge variant="connected" className="text-xs px-1.5 py-0.5 h-5 ml-2">
          {formatDuration(content.duration)}
        </Badge>
      </div>
      
      {content.type === "text" && (
        <div className="pl-6 mt-1 text-muted-foreground">
          <MarkdownRenderer content={content.text} className="text-sm" />
        </div>
      )}
      
      {content.type === "tool_use" && (
        <div className="space-y-3 pl-6">
          <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
            {/* <IconComponent name="Tool" className="h-3.5 w-3.5" /> */}
            <span>{content.name}</span>
          </div>
          
          {content.tool_input && (
            <InputSection 
              data={content.tool_input} 
              title="Input" 
              icon="ArrowDownCircle" 
            />
          )}
          
          {content.output && (
            <OutputSection 
              data={content.output} 
              title="Output" 
              icon="ArrowUpCircle"
              error={content.error}
            />
          )}
        </div>
      )}
    </div>
  );
}

function InputSection({ data, title, icon }: { data: any; title: string; icon: string }) {
  return (
    <div className="rounded-md overflow-hidden border border-border">
      <div className="bg-muted/30 py-1.5 px-3 flex items-center gap-1.5 border-b border-border">
        {/* <IconComponent name={icon} className="h-3.5 w-3.5 text-primary" /> */}
        <span className="text-xs font-medium">{title}</span>
      </div>
      <div className="bg-background p-2 overflow-x-auto">
        {typeof data === 'string' ? (
          <MarkdownRenderer content={data} className="text-xs m-0" />
        ) : (
          <pre className="text-xs m-0 whitespace-pre-wrap">{JSON.stringify(data, null, 2)}</pre>
        )}
      </div>
    </div>
  );
}

function OutputSection({ 
  data, 
  title, 
  icon, 
  error 
}: { 
  data: any; 
  title: string; 
  icon: string;
  error?: string | null;
}) {
  if (error) {
    return (
      <div className="rounded-md overflow-hidden border border-destructive/30">
        <div className="bg-destructive/10 py-1.5 px-3 flex items-center gap-1.5 border-b border-destructive/20">
          <IconComponent name="AlertCircle" className="h-3.5 w-3.5 text-destructive" />
          <span className="text-xs font-medium text-destructive">Error</span>
        </div>
        <div className="bg-background p-2 overflow-x-auto">
          <MarkdownRenderer content={error} className="text-xs m-0 text-destructive" />
        </div>
      </div>
    );
  }
  
  return (
    <div className="rounded-md overflow-hidden border border-border">
      <div className="bg-muted/30 py-1.5 px-3 flex items-center gap-1.5 border-b border-border">
        {/* <IconComponent name={icon} className="h-3.5 w-3.5 text-primary" /> */}
        <span className="text-xs font-medium">{title}</span>
      </div>
      <div className="bg-background p-2 overflow-x-auto">
        {typeof data === 'string' ? (
          <MarkdownRenderer content={data} className="text-xs m-0" />
        ) : (
          <pre className="text-xs m-0 whitespace-pre-wrap">{JSON.stringify(data, null, 2)}</pre>
        )}
      </div>
    </div>
  );
}

function formatDuration(ms: number): string {
  if (!ms) return "";
  if (ms < 1000) return `${ms}ms`;
  return `${(ms/1000).toFixed(1)}s`;
} 