import { useCallback, useEffect, useRef, useState, useMemo } from "react";
import { EventDeliveryType } from "@/constants/enums";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useChatService } from "@/controllers/API/queries/chat/use-chat-service";
import { Message, Session, MessageProperties, FileAttachment, ContentBlock } from "./types";
import { MessageBubble } from "./components";
import { useGetMessagesQuery } from "@/controllers/API/queries/messages";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import IconComponent from "@/components/common/genericIconComponent";
import { Button } from "@/components/ui/button";
import { useNavigate, useParams } from "react-router-dom";
import useFlowStore from "../../stores/flowStore";
import { useUtilityStore } from "@/stores/utilityStore";
import { useGetConfig } from "@/controllers/API/queries/config/use-get-config";
import ChatInput from "@/modals/IOModal/components/chatView/chatInput/chat-input";
import { useGetFlow } from "@/controllers/API/queries/flows/use-get-flow";
import useFlowsManagerStore from "../../stores/flowsManagerStore";
import { useMessagesStore } from "../../stores/messagesStore";
import { useDeleteMessages } from "@/controllers/API/queries/messages";
import useAlertStore from "../../stores/alertStore";
import { cn } from "@/utils/utils";
import ShadTooltip from "@/components/common/shadTooltipComponent";
import { FilePreviewType, IOModalPropsType } from "@/types/components";
import { usePostUploadFile } from "@/controllers/API/queries/files/use-post-upload-file";
import ShortUniqueId from "short-unique-id";
import { checkChatInput } from "@/utils/reactflowUtils";
import {
  ALLOWED_IMAGE_INPUT_EXTENSIONS,
  FS_ERROR_TEXT,
  SN_ERROR_TEXT,
} from "@/constants/constants";
import useFileSizeValidator from "@/shared/hooks/use-file-size-validator";
import BaseModal from "@/modals/baseModal";
import { SidebarOpenView } from "@/modals/IOModal/components/sidebar-open-view";
import { Separator } from "@/components/ui/separator";
import { TaskWorkflow } from "./components/WorkflowUI";
import "./components/WorkflowUI/customStyles.css";

export default function ChatModal({
  children,
  open,
  setOpen,
  disable,
  isPlayground,
  canvasOpen }: IOModalPropsType): JSX.Element {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [flowId, setFlowId] = useState(id || "");
  const [messages, setMessages] = useState<Message[]>([]);

  const [currentSession, setCurrentSession] = useState<string>("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [autoRefresh, setAutoRefresh] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const chatService = useChatService();
  const refreshIntervalRef = useRef<number | null>(null);
  const eventSourceRef = useRef<EventSource | null>(null);
  const setCurrentFlow = useFlowsManagerStore((state) => state.setCurrentFlow);
  const currentFlowId = useFlowsManagerStore((state) => state.currentFlowId);
  const [sessions, setSessions] = useState<string[]>(
    Array.from(
      new Set(
        messages
          .filter((message) => message.flow_id === currentFlowId)
          .map((message) => message.session_id),
      ),
    ),
  );
  const [sessionId, setSessionId] = useState<string>(flowId);
  const { mutateAsync: getFlow } = useGetFlow();
  const setErrorData = useAlertStore((state) => state.setErrorData);
  const setSuccessData = useAlertStore((state) => state.setSuccessData);
  const deleteSessionStore = useMessagesStore((state) => state.deleteSession);
  const { mutate: deleteSessionFunction } = useDeleteMessages();
  const storeMessages = useMessagesStore((state) => state.messages);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const inputRef = useRef<HTMLDivElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const { validateFileSize } = useFileSizeValidator(setErrorData);
  const { mutate: uploadFile } = usePostUploadFile();

  // File handling and drag/drop
  const [files, setFiles] = useState<FilePreviewType[]>([]);
  const [isDragging, setIsDragging] = useState(false);
  
  // Track when a message is sent to trigger scrolling
  const [scrollTrigger, setScrollTrigger] = useState(0);
  
  // Track which session last sent a message (for padding)
  const [lastMessageSession, setLastMessageSession] = useState<string | null>(null);

  // Refs for scrolling
  const messagesContainerRef = useRef<HTMLDivElement>(null);

  // All nodes in the flow
  const nodes = useFlowStore((state) => state.nodes);

  // Check if there is a ChatInput node in the flow
  const hasChatInputNode = checkChatInput(nodes);

  // Access FlowStore values after initialization
  const inputs = useFlowStore((state) => state.inputs).filter(
    (input) => input.type !== "ChatInput",
  );
  const chatInput = useFlowStore((state) => state.inputs).find(
    (input) => input.type === "ChatInput",
  );
  const outputs = useFlowStore((state) => state.outputs).filter(
    (output) => output.type !== "ChatOutput",
  );
  const chatOutput = useFlowStore((state) => state.outputs).find(
    (output) => output.type === "ChatOutput",
  );
  const buildFlow = useFlowStore((state) => state.buildFlow);
  const isBuilding = useFlowStore((state) => state.isBuilding);
  const setIsBuilding = useFlowStore((state) => state.setIsBuilding);

  const setChatValue = useUtilityStore((state) => state.setChatValueStore);
  const chatValue = useUtilityStore((state) => state.chatValueStore);
  const [visibleSession, setvisibleSession] = useState<string | undefined>(
    currentFlowId,
  );
  const deleteSession = useMessagesStore((state) => state.deleteSession);
  // Debug - log nodes and hasChatInputNode
  // useEffect(() => {
  //   console.log("Nodes:", nodes);
  //   console.log("Has ChatInput node:", hasChatInputNode);
  // }, [nodes, hasChatInputNode]);

  // Debug - log inputs when they change
  useEffect(() => {
    console.log("Current inputs:", inputs);
  }, [inputs]);

  // Debug - log chatInput when it changes
  useEffect(() => {
    console.log("ChatInput:", chatInput);
  }, [chatInput]);

  function handleDeleteSession(session_id: string) {
    deleteSessionFunction(
      {
        ids: messages
          .filter((msg) => msg.session_id === session_id)
          .map((msg) => msg.id),
      },
      {
        onSuccess: () => {
          setSuccessData({
            title: "Session deleted successfully.",
          });
          deleteSession(session_id);
          if (visibleSession === session_id) {
            setvisibleSession(undefined);
          }
        },
        onError: () => {
          setErrorData({
            title: "Error deleting Session.",
          });
        },
      },
    );
  }

  function startView() {
    if (!chatInput && !chatOutput) {
      if (inputs.length > 0) {
        return inputs[0];
      } else {
        return outputs[0];
      }
    } else {
      return undefined;
    }
  }

  const [selectedViewField, setSelectedViewField] = useState<
    { type: string; id: string } | undefined
  >(startView());

  // Setup drag and drop handlers
  const dragOver = (e: React.DragEvent) => {
    e.preventDefault();
    if (e.dataTransfer.types.some((type) => type === "Files")) {
      setIsDragging(true);
    }
  };

  const dragEnter = (e: React.DragEvent) => {
    if (e.dataTransfer.types.some((type) => type === "Files")) {
      setIsDragging(true);
    }
    e.preventDefault();
  };

  const dragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const drop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);

    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFileUpload(e.dataTransfer.files);
    }
  };

  // Handle file upload
  const handleFileUpload = (fileList: FileList) => {
    const file = fileList[0];
    if (file) {
      const fileExtension = file.name.split(".").pop()?.toLowerCase();

      if (!validateFileSize(file)) {
        return;
      }

      if (
        !fileExtension ||
        !ALLOWED_IMAGE_INPUT_EXTENSIONS.includes(fileExtension)
      ) {
        setErrorData({
          title: "Error uploading file",
          list: [FS_ERROR_TEXT, SN_ERROR_TEXT],
        });
        return;
      }

      const uid = new ShortUniqueId();
      const id = uid.randomUUID(10);
      const type = file.type.split("/")[0];

      setFiles((prevFiles) => [
        ...prevFiles,
        { file, loading: true, error: false, id, type },
      ]);

      uploadFile(
        { file, id: flowId },
        {
          onSuccess: (data) => {
            setFiles((prev) => {
              const newFiles = [...prev];
              const updatedIndex = newFiles.findIndex((f) => f.id === id);
              newFiles[updatedIndex].loading = false;
              newFiles[updatedIndex].path = data.file_path;
              return newFiles;
            });
          },
          onError: (error) => {
            setFiles((prev) => {
              const newFiles = [...prev];
              const updatedIndex = newFiles.findIndex((f) => f.id === id);
              newFiles[updatedIndex].loading = false;
              newFiles[updatedIndex].error = true;
              return newFiles;
            });
            setErrorData({
              title: "Error uploading file",
              list: [error.response?.data?.detail],
            });
          },
        },
      );
    }
  };

  // Handle file change from input element
  const handleFileChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    if (event.target.files && event.target.files.length > 0) {
      handleFileUpload(event.target.files);
      event.target.value = ""; // Reset the input
    }
  };

  // Handle paste events for files
  useEffect(() => {
    const handlePaste = (event: ClipboardEvent) => {
      const items = event.clipboardData?.items;
      if (items) {
        for (let i = 0; i < items.length; i++) {
          const blob = items[i].getAsFile();
          if (blob) {
            const fileList = new DataTransfer();
            fileList.items.add(blob);
            handleFileUpload(fileList.files);
            break;
          }
        }
      }
    };

    document.addEventListener("paste", handlePaste);
    return () => {
      document.removeEventListener("paste", handlePaste);
    };
  }, [flowId, isBuilding]);


  // Load flow data when component mounts and flowId is available
  useEffect(() => {
    if (flowId) {
      const loadFlowData = async () => {
        try {
          setIsLoading(true);
          const flow = await getFlow({ id: flowId });
          // This will also set up the inputs and outputs in FlowStore
          setCurrentFlow(flow);
          setIsLoading(false);
        } catch (error) {
          console.error("Error loading flow:", error);
          setError("Failed to load flow data. Please check your Flow ID and try again.");
          setIsLoading(false);
        }
      };

      loadFlowData();
    }
  }, [flowId, getFlow, setCurrentFlow]);

  const inputTypes = inputs.map((obj) => obj.type);

  // Redirect to home if no ID is provided
  useEffect(() => {
    if (!id) {
      navigate('/');
    }
  }, [id, navigate]);

  // Update URL when flowId changes
  useEffect(() => {
    if (flowId && flowId !== id) {
      navigate(`/chat/${flowId}`);
    }
  }, [flowId, id, navigate]);

  // Initialize flowId from URL parameter
  useEffect(() => {
    if (id && id !== flowId) {
      setFlowId(id);
    }
  }, [id]);

  // Memoize the conversion of timestamps once for efficiency
  const standardizeTimestamp = useCallback((timestamp: string) => {
    if (!timestamp) return '';

    // Simplify the timestamp standardization by using a regex replacement
    // This is more efficient than the string manipulations in the original
    return timestamp.replace(/[^0-9T:-]/g, '');
  }, []);

  // Make sure fetchMessages is defined BEFORE it is used in the useEffect
  const fetchMessages = useCallback(async (flowId: string) => {
    try {
      setError(null);
      const response = await chatService.getMessages(flowId);
      
      // Convert and set messages in one operation to avoid redundant processing
      const mappedMessages = response.map(msg => {
        // Create properties object efficiently
        const messageProperties: MessageProperties = {
          text_color: msg.properties?.text_color || "#000000",
          background_color: msg.properties?.background_color || "#ffffff",
          edited: msg.edit || false,
          source: {
            id: msg.properties?.source?.id || null,
            display_name: msg.properties?.source?.display_name || null,
            source: msg.properties?.source?.source || null,
          },
          icon: msg.properties?.icon || "",
          allow_markdown: msg.properties?.allow_markdown || true,
          positive_feedback: null,
          state: msg.properties?.state || "",
          targets: msg.properties?.targets || [],
        };

        // Process files only once
        const convertedFiles: FileAttachment[] = msg.files && Array.isArray(msg.files)
          ? msg.files.map((file: string | FileAttachment) => ({
            path: typeof file === 'string' ? file : file.path,
            type: typeof file === 'string' ? file.split('.').pop() || 'unknown' : file.type,
            name: typeof file === 'string' ? file.split('/').pop() || file : file.name
          }))
          : [];

        // Make sure content_blocks match the expected type
        const contentBlocks = msg.content_blocks ? msg.content_blocks.map(block => ({
          title: block.title || "",
          contents: block.contents.map(content => ({
            type: content.type || "text",
            duration: content.duration || 0,
            header: content.header || { title: "", icon: "" },
            text: 'text' in content ? content.text : '',
            name: 'name' in content ? content.name : undefined,
            tool_input: 'tool_input' in content ? content.tool_input : undefined,
            output: 'output' in content ? content.output : undefined,
            error: 'error' in content ? content.error : null
          })),
          allow_markdown: block.allow_markdown || true,
          media_url: typeof block.media_url === 'string' ? block.media_url : null
        })) : [];

        // Return the fully formatted message
        return {
          id: msg.id,
          flow_id: msg.flow_id,
          timestamp: standardizeTimestamp(msg.timestamp),
          sender: msg.sender,
          sender_name: msg.sender_name,
          session_id: msg.session_id,
          text: msg.text,
          files: convertedFiles,
          edit: msg.edit,
          properties: messageProperties,
          category: msg.category || "",
          content_blocks: contentBlocks,
        } as Message;
      }).sort((a, b) => 
        new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
      );

      setMessages(mappedMessages);
    } catch (error) {
      console.error("Error fetching messages:", error);
      setError("Failed to fetch messages. Please check your Flow ID and try again.");
    }
  }, [standardizeTimestamp]);

  // Add this near other state declarations at the top
  const { isFetched: messagesFetched, refetch } = useGetMessagesQuery(
    {
      mode: "union",
      id: flowId,
    },
    { enabled: !!flowId },
  );

  // Now your useEffect can use messagesFetched without error
  useEffect(() => {
    if (flowId && messagesFetched) {
      const relevantMessages = storeMessages.filter(msg => msg.flow_id === flowId);
      
      // Only update if store messages are different
      const storeMessageIds = new Set(relevantMessages.map(msg => msg.id));
      const currentMessageIds = new Set(messages.filter(msg => !msg.id.startsWith('temp-')).map(msg => msg.id));
      
      // Check if the sets are different
      const needsUpdate = storeMessageIds.size !== currentMessageIds.size || 
        Array.from(storeMessageIds).some(id => !currentMessageIds.has(id));
      
      if (needsUpdate) {
        // Convert store message type to ChatPage message type  
        const convertedMessages = relevantMessages.map(msg => {
          const messageProperties: MessageProperties = {
            text_color: msg.properties?.text_color || "#000000",
            background_color: msg.properties?.background_color || "#ffffff",
            edited: msg.edit || false,
            source: {
              id: msg.properties?.source?.id || null,
              display_name: msg.properties?.source?.display_name || null,
              source: msg.properties?.source?.source || null,
            },
            icon: msg.properties?.icon || "",
            allow_markdown: msg.properties?.allow_markdown || true,
            positive_feedback: null,
            state: msg.properties?.state || "",
            targets: msg.properties?.targets || [],
          };

          const convertedFiles: FileAttachment[] = msg.files && Array.isArray(msg.files)
            ? msg.files.map((file: string | FileAttachment) => ({
              path: typeof file === 'string' ? file : file.path,
              type: typeof file === 'string' ? file.split('.').pop() || 'unknown' : file.type,
              name: typeof file === 'string' ? file.split('/').pop() || file : file.name
            }))
            : [];

          // Make sure content_blocks match the expected type
          const contentBlocks = msg.content_blocks ? msg.content_blocks.map(block => ({
            title: block.title || "",
            contents: block.contents.map(content => ({
              type: content.type || "text",
              duration: content.duration || 0,
              header: content.header || { title: "", icon: "" },
              text: 'text' in content ? content.text : '',
              name: 'name' in content ? content.name : undefined,
              tool_input: 'tool_input' in content ? content.tool_input : undefined,
              output: 'output' in content ? content.output : undefined,
              error: 'error' in content ? content.error : null
            })),
            allow_markdown: block.allow_markdown || true,
            media_url: typeof block.media_url === 'string' ? block.media_url : null
          })) : [];

          return {
            id: msg.id,
            flow_id: msg.flow_id,
            timestamp: standardizeTimestamp(msg.timestamp),
            sender: msg.sender,
            sender_name: msg.sender_name,
            session_id: msg.session_id,
            text: msg.text,
            files: convertedFiles,
            edit: msg.edit,
            properties: messageProperties,
            category: msg.category || "",
            content_blocks: contentBlocks,
          } as Message;
        });

        // Find any temporary messages that aren't in the store yet
        const tempMessages = messages.filter(msg =>
          msg.id.startsWith('temp-') &&
          !convertedMessages.some(storeMsg => storeMsg.text === msg.text && storeMsg.sender === msg.sender)
        );

        // Keep the original order of store messages and append temporary messages
        setMessages([...convertedMessages, ...tempMessages]);
      }
    }
  }, [storeMessages, flowId, messagesFetched, standardizeTimestamp, messages]);

  // Memoize the filtered messages to prevent recalculation on every render
  const filteredMessages = useMemo(() => {
    // When creating a new chat with no visible session, show no messages
    if (!visibleSession) {
      return [];
    }

    // For existing sessions, show only messages for that session and properly convert for UI
    return messages
      .filter(message => message.session_id === visibleSession)
      .map(message => ({
        ...message,
        background_color: message.properties.background_color,
        text_color: message.properties.text_color,
        files: Array.isArray(message.files)
          ? message.files.map(file => typeof file === 'string' ? file : file.path)
          : [],
        content_blocks: message.content_blocks?.map(block => ({
          ...block,
          component: 'default',
          media_url: block.media_url ? [block.media_url] : undefined,
          contents: block.contents.map(content => {
            if (content.type === 'tool_use') {
              return {
                type: 'tool_use' as const,
                duration: content.duration,
                header: content.header,
                name: content.name || "",
                tool_input: content.tool_input,
                output: content.output,
                error: content.error
              };
            } else {
              return {
                type: 'text' as const,
                duration: content.duration,
                header: content.header,
                text: content.text
              };
            }
          })
        })),
        properties: {
          ...message.properties,
          background_color: undefined,
          text_color: undefined
        }
      }))
      // Sort messages by timestamp using the standardized format
      .sort((a, b) => {
        const timestampA = standardizeTimestamp(a.timestamp);
        const timestampB = standardizeTimestamp(b.timestamp);
        return new Date(timestampA).getTime() - new Date(timestampB).getTime();
      });
  }, [messages, visibleSession, standardizeTimestamp]);

  // Update sessions when messages change
  useEffect(() => {
    const sessions = new Set<string>();
    messages
      .filter((message) => message.flow_id === flowId)
      .forEach((row) => {
        sessions.add(row.session_id);
      });

    setSessions((prev) => {
      const newSessions = Array.from(sessions);
      if (prev.length < newSessions.length) {
        // set the new session as visible
        setvisibleSession(
          newSessions[newSessions.length - 1],
        );
      }
      return newSessions;
    });
  }, [messages, flowId]);

  // Handle session visibility changes
  useEffect(() => {
    if (!visibleSession) {
      // Generate a new session ID
      const newSessionId = `Session ${new Date().toLocaleString("en-US", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", hour12: false, second: "2-digit", timeZone: "UTC" })}`;

      // Set it as the current session
      setSessionId(newSessionId);

      // Clear all temporary messages
      setMessages(prevMessages => prevMessages.filter(msg => !msg.id.startsWith('temp-')));

      // Don't add to sessions list yet - it will be added when it has messages

      // Don't make the new session visible until it has messages
    } else if (visibleSession) {
      setSessionId(visibleSession);
      if (selectedViewField?.type === "Session") {
        setSelectedViewField({
          id: visibleSession,
          type: "Session",
        });
      }
      
      // Clear padding when switching sessions if not the last message session
      if (messagesEndRef.current && visibleSession !== lastMessageSession) {
        messagesEndRef.current.style.paddingBottom = "0px";
      }
    }
  }, [visibleSession, lastMessageSession]);

  // Fetch messages when flowId changes or component mounts
  useEffect(() => {
    if (flowId) {
      fetchMessages(flowId);
    }
  }, [flowId]);

  // Setup auto-refresh
  useEffect(() => {
    // Clear any existing interval
    if (refreshIntervalRef.current) {
      window.clearInterval(refreshIntervalRef.current);
      refreshIntervalRef.current = null;
    }

    // Set up new interval if autoRefresh is enabled, streaming is disabled, and we have a flowId
    if (autoRefresh && flowId && !shouldStreamEvents()) {
      refreshIntervalRef.current = window.setInterval(() => {
        fetchMessages(flowId);
      }, 5000); // Refresh every 5 seconds
    }

    // Cleanup function
    return () => {
      if (refreshIntervalRef.current) {
        window.clearInterval(refreshIntervalRef.current);
      }
    };
  }, [autoRefresh, flowId, shouldStreamEvents]);

  const config = useGetConfig();
  function shouldStreamEvents() {
    return config.data?.event_delivery === EventDeliveryType.STREAMING;
  }

  // Cleanup event source on unmount
  useEffect(() => {
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
    };
  }, []);

  // Update sessions when messages change
  useEffect(() => {
    const sessions = new Set<string>();
    messages
      .filter((message) => message.flow_id === flowId)
      .forEach((row) => {
        sessions.add(row.session_id);
      });

    setSessions((prev) => {
      const newSessions = Array.from(sessions);
      if (prev.length < newSessions.length) {
        // set the new session as visible
        setvisibleSession(
          newSessions[newSessions.length - 1],
        );
      }
      return newSessions;
    });
  }, [messages, flowId]);

  // Handle session visibility changes
  useEffect(() => {
    if (!visibleSession) {
      // Generate a new session ID
      const newSessionId = `Session ${new Date().toLocaleString("en-US", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", hour12: false, second: "2-digit", timeZone: "UTC" })}`;

      // Set it as the current session
      setSessionId(newSessionId);

      // Clear all temporary messages
      setMessages(prevMessages => prevMessages.filter(msg => !msg.id.startsWith('temp-')));

      // Don't add to sessions list yet - it will be added when it has messages

      // Don't make the new session visible until it has messages
    } else if (visibleSession) {
      setSessionId(visibleSession);
      if (selectedViewField?.type === "Session") {
        setSelectedViewField({
          id: visibleSession,
          type: "Session",
        });
      }
    }
  }, [visibleSession]);

  // Fetch messages when flowId changes or component mounts
  useEffect(() => {
    if (flowId) {
      fetchMessages(flowId);
    }
  }, [flowId]);

  // Setup auto-refresh
  useEffect(() => {
    // Clear any existing interval
    if (refreshIntervalRef.current) {
      window.clearInterval(refreshIntervalRef.current);
      refreshIntervalRef.current = null;
    }

    // Set up new interval if autoRefresh is enabled, streaming is disabled, and we have a flowId
    if (autoRefresh && flowId && !shouldStreamEvents()) {
      refreshIntervalRef.current = window.setInterval(() => {
        fetchMessages(flowId);
      }, 5000); // Refresh every 5 seconds
    }

    // Cleanup function
    return () => {
      if (refreshIntervalRef.current) {
        window.clearInterval(refreshIntervalRef.current);
      }
    };
  }, [autoRefresh, flowId, shouldStreamEvents]);

  // Update local messages when store messages change
  useEffect(() => {
    if (flowId && messagesFetched) {
      const relevantMessages = storeMessages.filter(msg => msg.flow_id === flowId);

      // Convert store message type to ChatPage message type  
      const convertedMessages = relevantMessages.map(msg => {
        const messageProperties: MessageProperties = {
          text_color: msg.properties?.text_color || "#000000",
          background_color: msg.properties?.background_color || "#ffffff",
          edited: msg.edit || false,
          source: {
            id: msg.properties?.source?.id || null,
            display_name: msg.properties?.source?.display_name || null,
            source: msg.properties?.source?.source || null,
          },
          icon: msg.properties?.icon || "",
          allow_markdown: msg.properties?.allow_markdown || true,
          positive_feedback: null,
          state: msg.properties?.state || "",
          targets: msg.properties?.targets || [],
        };

        const convertedFiles: FileAttachment[] = msg.files && Array.isArray(msg.files)
          ? msg.files.map((file: string | FileAttachment) => ({
            path: typeof file === 'string' ? file : file.path,
            type: typeof file === 'string' ? file.split('.').pop() || 'unknown' : file.type,
            name: typeof file === 'string' ? file.split('/').pop() || file : file.name
          }))
          : [];

        return {
          id: msg.id,
          flow_id: msg.flow_id,
          timestamp: standardizeTimestamp(msg.timestamp),
          sender: msg.sender,
          sender_name: msg.sender_name,
          session_id: msg.session_id,
          text: msg.text,
          files: convertedFiles,
          edit: msg.edit,
          properties: messageProperties,
          category: msg.category || "",
          content_blocks: convertContentBlocks(msg.content_blocks || []),
        } as Message;
      }) as unknown as Message[];

      // Log converted messages for debugging
      console.log("Converted Messages:", convertedMessages.map(m => ({
        id: m.id,
        timestamp: m.timestamp,
        sender: m.sender
      })));

      // Find any temporary messages that aren't in the store yet
      const tempMessages = messages.filter(msg =>
        msg.id.startsWith('temp-') &&
        !convertedMessages.some(storeMsg => storeMsg.text === msg.text && storeMsg.sender === msg.sender)
      );

      // Keep the original order of store messages and append temporary messages
      const finalMessages = [...convertedMessages, ...tempMessages];

      // Log final messages for debugging
      console.log("Final Messages:", finalMessages.map(m => ({
        id: m.id,
        timestamp: m.timestamp,
        sender: m.sender
      })));

      setMessages(finalMessages);
    }
  }, [storeMessages, flowId, messagesFetched, standardizeTimestamp]);

  // Remove the conflicting useEffect for scrolling
  useEffect(() => {
    // This line conflicts with the other scrolling mechanisms, removing it
    // messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [filteredMessages]);

  // Handle file delete
  const handleDeleteFile = (file: FilePreviewType) => {
    setFiles((prev) => prev.filter((f) => f.id !== file.id));
  };

  // Update the refresh button click handler
  const handleRefresh = () => {
    if (flowId) {
      // Force a refetch of messages
      refetch();
    }
  };

  // Responsive sidebar
  useEffect(() => {
    const handleResize = () => {
      if (window.innerWidth < 1024) {
        setSidebarOpen(false);
      } else {
        setSidebarOpen(true);
      }
    };

    handleResize();
    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
    };
  }, []);

  // Remove the ResizeObserver effect that's causing scrolling on load
  useEffect(() => {
    if (!messagesEndRef.current) return;
    
    // Create a ResizeObserver to handle changes to the container size
    const resizeObserver = new ResizeObserver(() => {
      // Don't auto-scroll here, as this fires on component mount
      // messagesEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
    });
    
    // Observe the messages container
    resizeObserver.observe(messagesEndRef.current);
    
    // Cleanup function
    return () => {
      resizeObserver.disconnect();
    };
  }, []); // Empty dependency array to only run once

  // Force scroll to bottom after sending a message
  const scrollToBottom = useCallback((force = false): void => {
    // Immediate scroll - no timeout delay
    if (messagesEndRef.current) {
      // Add padding only for the session where message was sent
      if (sessionId === lastMessageSession) {
        messagesEndRef.current.style.paddingBottom = "110px";
      }
      
      // Scroll immediately when forced, otherwise smooth
      messagesEndRef.current.scrollIntoView({ 
        behavior: "auto", // Always use auto for immediate effect
        block: "start" 
      });
      
      // Use direct scrolling for immediate effect
      if (messagesContainerRef.current) {
        messagesContainerRef.current.scrollTo({
          top: messagesEndRef.current.offsetTop,
          behavior: "auto" // Always use auto for immediate effect
        });
      }
    }
  }, [sessionId, lastMessageSession]);

  // Effect to handle scrolling when messages change
  useEffect(() => {
    if (scrollTrigger > 0) {
      // Use RAF to ensure DOM is updated before scrolling
      requestAnimationFrame(() => {
        scrollToBottom(true);
      });
    }
  }, [scrollTrigger, scrollToBottom]);

  // Optimize the sendMessage function
  const sendMessage = useCallback(
    async ({
      repeat = 1,
      files,
    }: {
      repeat: number;
      files?: string[];
    }): Promise<void> => {
      if (isBuilding) return;

      // Set this session as the last message session
      setLastMessageSession(sessionId);
      
      // Trigger scroll BEFORE adding the message
      setScrollTrigger(prev => prev + 1);

      // Generate a temporary message ID once
      const tempId = `temp-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
      const messageText = chatValue;
      const timestamp = standardizeTimestamp(new Date().toISOString());

      // Create user message once with all required properties
      const userMessage: Message = {
        id: tempId,
        flow_id: flowId,
        timestamp,
        sender: "User",
        sender_name: "You",
        session_id: sessionId,
        text: messageText,
        files: [],
        edit: false,
        properties: {
          text_color: "#000000",
          background_color: "#ffffff",
          edited: false,
          source: { id: null, display_name: null, source: null },
          icon: "",
          allow_markdown: true,
          positive_feedback: null,
          state: "",
          targets: [],
        },
        category: "",
        content_blocks: [],
      };

      // Clear the input before updating messages
      setChatValue("");

      // Add the message to messages array AFTER triggering scroll
      setMessages(prevMessages => [...prevMessages, userMessage]);

      // Update session state only when needed
      setSessions(prev => {
        if (!prev.includes(sessionId)) {
          return [...prev, sessionId];
        }
        return prev;
      });

      // Make sure this session is visible
      setvisibleSession(sessionId);

      // Reset files array
      const filesToUse = files || [];
      
      // Send the message to the API once per repeat
      for (let i = 0; i < repeat; i++) {
        try {
          await buildFlow({
            input_value: messageText,
            startNodeId: chatInput?.id,
            files: filesToUse,
            silent: true,
            session: sessionId,
            stream: shouldStreamEvents(),
          });
        } catch (err) {
          console.error(err);
        }
      }

      // Clear files after sending
      setFiles([]);
    },
    [isBuilding, chatValue, chatInput?.id, sessionId, buildFlow, shouldStreamEvents, flowId, standardizeTimestamp, setFiles, setChatValue],
  );

  function convertContentBlocks(blocks: any[]): ContentBlock[] {
    return blocks?.map(block => ({
      title: block.title || '',
      contents: block.contents || [],
      allow_markdown: block.allow_markdown ?? true,
      media_url: Array.isArray(block.media_url) ? block.media_url[0] || null : block.media_url
    })) || [];
  }

  return (
    <BaseModal
      open={open}
      setOpen={setOpen}
      disable={disable}
      type={isPlayground ? "full-screen" : undefined}
      onSubmit={() => sendMessage({ repeat: 1 })}
      size="x-large"
      className="!rounded-[12px] p-0"
    >
      <BaseModal.Trigger>{children}</BaseModal.Trigger>
      {/* TODO ADAPT TO ALL TYPES OF INPUTS AND OUTPUTS */}
      <BaseModal.Content overflowHidden className="h-full">
        {open && (
          <div className="flex-max-width h-full">
            <div
              className={cn(
                "flex h-full flex-shrink-0 flex-col justify-start overflow-hidden transition-all duration-300",
                sidebarOpen
                  ? "absolute z-50 lg:relative lg:w-1/5 lg:max-w-[280px]"
                  : "w-0",
              )}
            >
              <div className="flex h-full flex-col overflow-y-auto border-r border-border bg-muted p-4 text-center custom-scroll dark:bg-canvas">
                <div className="flex items-center gap-2 pb-8">
                  <ShadTooltip
                    styleClasses="z-50"
                    side="right"
                    content="Hide sidebar"
                  >
                    <Button
                      variant="ghost"
                      className="flex h-8 w-8 items-center justify-center !p-0"
                      onClick={() => setSidebarOpen(!sidebarOpen)}
                    >
                      <IconComponent
                        name={sidebarOpen ? "PanelLeftClose" : "PanelLeftOpen"}
                        className="h-[18px] w-[18px] text-ring"
                      />
                    </Button>
                  </ShadTooltip>
                  {sidebarOpen && (
                    <div className="font-semibold">Playground</div>
                  )}
                </div>
                {sidebarOpen && (
                  <SidebarOpenView
                    sessions={sessions}
                    setSelectedViewField={setSelectedViewField}
                    setvisibleSession={setvisibleSession}
                    handleDeleteSession={handleDeleteSession}
                    visibleSession={visibleSession}
                    selectedViewField={selectedViewField}
                  />
                )}
              </div>
            </div>
            <div className={cn(
              "flex h-full w-full flex-col justify-between p-4",
              selectedViewField ? "hidden" : ""
            )}>
              <div className="mb-4 h-[5%] text-[16px] font-semibold">
                <div className="flex justify-between items-center">
                  <div>
                    {visibleSession && sessions.length > 0 && sidebarOpen && (
                      <div className="hidden lg:block">
                        {visibleSession === flowId
                          ? "Default Session"
                          : `${visibleSession}`}
                      </div>
                    )}
                    <div className={cn(sidebarOpen ? "lg:hidden" : "")}>
                      <div className="flex items-center gap-2">
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => setSidebarOpen(true)}
                          className="h-8 w-8"
                        >
                          <IconComponent
                            name="PanelLeftOpen"
                            className="h-[18px] w-[18px] text-ring"
                          />
                        </Button>
                        <div className="font-semibold">Playground</div>
                      </div>
                    </div>
                  </div>

                  <div className={cn(sidebarOpen ? "hidden" : "flex")}>
                    <ShadTooltip side="bottom" styleClasses="z-50" content="New Chat">
                      <Button
                        className="h-[32px] w-[32px] hover:bg-secondary-hover"
                        variant="ghost"
                        size="icon"
                        onClick={() => {
                          setvisibleSession(undefined);
                          setSelectedViewField(undefined);
                        }}
                      >
                        <IconComponent
                          name="Plus"
                          className="h-[18px] w-[18px] text-ring"
                        />
                      </Button>
                    </ShadTooltip>
                  </div>
                </div>
              </div>

              <div
                className={cn(
                  visibleSession ? "h-[95%]" : "h-full",
                  sidebarOpen
                    ? "pointer-events-none blur-sm lg:pointer-events-auto lg:blur-0"
                    : ""
                )}
              >
                <div className="flex h-full w-full flex-col rounded-md"
                  onDragOver={dragOver}
                  onDragEnter={dragEnter}
                  onDragLeave={dragLeave}
                  onDrop={drop}
                >
                  <div 
                    ref={messagesContainerRef} 
                    className="chat-message-div m-auto w-full max-w-[768px] md:w-5/6 overflow-y-auto"
                    style={{ 
                      height: "calc(100vh - 250px)", /* Make the container taller to allow scrolling */
                      display: "flex",
                      flexDirection: "column",
                      scrollBehavior: "smooth" // Add smooth scrolling to container
                    }}
                  >
                    {error && (
                      <Alert variant="destructive" className="mb-4">
                        <IconComponent name="AlertCircle" className="h-4 w-4" />
                        <AlertTitle>Error</AlertTitle>
                        <AlertDescription>{error}</AlertDescription>
                      </Alert>
                    )}

                    {filteredMessages.length === 0 ? (
                      <div className="flex h-full w-full flex-col items-center justify-center">
                        <div className="flex flex-col items-center justify-center gap-4 p-8">
                          <div className="flex flex-col items-center justify-center">
                            <h3 className="mt-2 pb-2 text-2xl font-semibold text-primary">
                              New chat
                            </h3>
                            <p className="text-lg text-muted-foreground">
                              Test your flow with a chat prompt
                            </p>
                          </div>
                        </div>
                      </div>
                    ) : (
                      <div className="w-full">
                        <TaskWorkflow 
                          messages={filteredMessages}
                          query={filteredMessages.find(m => m.sender === "User")?.text}
                        />
                        <div 
                          id="chat-end" 
                          ref={messagesEndRef} 
                          style={{ 
                            height: "20px",
                            width: "100%",
                            transition: "padding-bottom 0.5s ease-out" // Slower, smoother transition
                          }} 
                        />
                      </div>
                    )}
                  </div>

                  <div className="m-auto w-full max-w-[768px] md:w-5/6">
                    <ChatInput
                      noInput={!hasChatInputNode}
                      sendMessage={sendMessage}
                      isDragging={isDragging}
                      files={files}
                      setFiles={setFiles}
                      inputRef={inputRef}
                    />

                    {/* Hidden file input for trigger with button */}
                    <input
                      type="file"
                      ref={fileInputRef}
                      onChange={handleFileChange}
                      className="hidden"
                      accept={ALLOWED_IMAGE_INPUT_EXTENSIONS.map(ext => `.${ext}`).join(',')}
                    />
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}
      </BaseModal.Content>
    </BaseModal>
  );
}