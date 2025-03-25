import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeMathjax from 'rehype-mathjax';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { tomorrow } from 'react-syntax-highlighter/dist/cjs/styles/prism';
import { cn } from '@/utils/utils';
import CodeTabsComponent from '@/components/core/codeTabsComponent/ChatCodeTabComponent';

interface MarkdownRendererProps {
  content: string;
  className?: string;
}

export function MarkdownRenderer({ content, className }: MarkdownRendererProps) {
  return (
    <ReactMarkdown
      className={cn("prose prose-sm max-w-none dark:prose-invert", className)}
      remarkPlugins={[remarkGfm, remarkMath]}
      rehypePlugins={[rehypeMathjax]}
      components={{
        pre({ node, ...props }) {
          // This prevents wrapping code blocks in an additional pre tag
          return <>{props.children}</>;
        },
        p({ node, ...props }) {
          // This ensures paragraphs are rendered properly
          return <p className="break-words">{props.children}</p>;
        },
        code({ node, inline, className, children, ...props }) {
          // Handle the code content
          let content = children as string;
          if (
            Array.isArray(children) &&
            children.length === 1 &&
            typeof children[0] === "string"
          ) {
            content = children[0] as string;
          }

          // Special handling for "Executed **" patterns
          if (typeof content === "string" && 
              !inline && 
              !className && 
              content.includes("Executed **")) {
            return <span className="text-primary">{content}</span>;
          }

          const match = /language-(\w+)/.exec(className || '');
          return !inline && match ? (
            <CodeTabsComponent
              language={match[1]}
              code={String(content).replace(/\n$/, '')}
            />
          ) : (
            <code className={cn("bg-muted px-1 py-0.5 rounded text-sm", className)} {...props}>
              {content}
            </code>
          );
        },
        // Style tables to match the rest of the UI
        table({node, ...props}) {
          return (
            <div className="my-4 w-full overflow-auto rounded-md border">
              <table className="w-full" {...props} />
            </div>
          );
        },
        th({node, ...props}) {
          return <th className="border-b border-r px-4 py-2 text-left font-semibold last:border-r-0" {...props} />;
        },
        td({node, ...props}) {
          return <td className="border-b border-r px-4 py-2 last:border-r-0" {...props} />;
        },
        // Add proper styling for links
        a({node, ...props}) {
          return (
            <a 
              className="text-primary underline decoration-primary underline-offset-2" 
              target="_blank" 
              rel="noopener noreferrer" 
              {...props} 
            />
          );
        },
        // Improve styling for blockquotes
        blockquote({node, ...props}) {
          return (
            <blockquote 
              className="my-2 border-l-4 border-muted-foreground/30 pl-4 italic" 
              {...props} 
            />
          );
        }
      }}
    >
      {content}
    </ReactMarkdown>
  );
} 