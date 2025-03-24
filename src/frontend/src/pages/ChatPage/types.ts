export interface Message {
  id: string;
  flow_id: string;
  timestamp: string;
  sender: string;
  sender_name: string;
  session_id: string;
  text: string;
  files: string | Array<FileAttachment>;
  edit: boolean;
  properties: MessageProperties;
  category: string;
  content_blocks: ContentBlock[];
}

export interface FileAttachment {
  path: string;
  type: string;
  name: string;
}

export interface MessageProperties {
  text_color: string;
  background_color: string;
  edited: boolean;
  source: {
    id: string | null;
    display_name: string | null;
    source: string | null;
  };
  icon: string;
  allow_markdown: boolean;
  positive_feedback: null;
  state: string;
  targets: any[];
}

export interface ContentBlock {
  title: string;
  contents: BlockContent[];
  allow_markdown: boolean;
  media_url: string | null;
}

export interface BlockContent {
  type: string;
  duration: number;
  header: {
    title: string;
    icon: string;
  };
  text: string;
  name?: string;
  tool_input?: any;
  output?: any;
  error?: string | null;
}

export interface Session {
  id: string;
  name: string;
  timestamp?: string;
}

export interface ChatInputProps {
  onSendMessage: (options: { repeat: number; files?: string[] }) => Promise<void>;
  disabled: boolean;
  loading: boolean;
  placeholder?: string;
}

export interface MessageBubbleProps {
  message: Message;
  isUser: boolean;
} 