import LangflowLogo from "@/assets/LangflowLogo.svg?react";
import ChainLogo from "@/assets/logo.svg?react";
import { TextEffectPerChar } from "@/components/ui/textAnimation";
import { ENABLE_NEW_LOGO } from "@/customization/feature-flags";
import { track } from "@/customization/utils/analytics";
import { useMessagesStore } from "@/stores/messagesStore";
import { useUtilityStore } from "@/stores/utilityStore";
import { memo, useCallback, useEffect, useMemo, useRef, useState, useTransition } from "react";
import useTabVisibility from "../../../../shared/hooks/use-tab-visibility";
import useFlowsManagerStore from "../../../../stores/flowsManagerStore";
import useFlowStore from "../../../../stores/flowStore";
import { ChatMessageType } from "../../../../types/chat";
import { chatViewProps } from "../../../../types/components";
import FlowRunningSqueleton from "../flow-running-squeleton";
import ChatInput from "./chatInput/chat-input";
import useDragAndDrop from "./chatInput/hooks/use-drag-and-drop";
import { useFileHandler } from "./chatInput/hooks/use-file-handler";
import ChatMessage from "./chatMessage/chat-message";
import { v4 as uuidv4 } from 'uuid';

// Constants for localStorage
const EDITED_MESSAGES_STORAGE_KEY = 'langflow_edited_messages';

// Enhanced memo function that strictly compares all relevant props
const MemoizedChatMessage = memo(ChatMessage, (prevProps, nextProps) => {
  if (prevProps.chat.id !== nextProps.chat.id) return false;
  if (prevProps.lastMessage !== nextProps.lastMessage) return false;
  
  // For user messages (optimistic ones), be strict about preserving identity
  if (prevProps.chat.isSend && nextProps.chat.isSend && 
      prevProps.chat.id === nextProps.chat.id) {
    return true;
  }
  
  // For other messages, do deep comparison
  return (
    prevProps.chat.message === nextProps.chat.message &&
    prevProps.chat.session === nextProps.chat.session &&
    JSON.stringify(prevProps.chat.content_blocks) === JSON.stringify(nextProps.chat.content_blocks) &&
    JSON.stringify(prevProps.chat.properties) === JSON.stringify(nextProps.chat.properties)
  );
});

export default function ChatView({
  sendMessage,
  visibleSession,
  focusChat,
  closeChat,
  standardizeTimestamp,
}: chatViewProps): JSX.Element {
  const flowPool = useFlowStore((state) => state.flowPool);
  const inputs = useFlowStore((state) => state.inputs);
  const currentFlowId = useFlowsManagerStore((state) => state.currentFlowId);
  const messagesRef = useRef<HTMLDivElement | null>(null);
  const [chatHistory, setChatHistory] = useState<ChatMessageType[] | undefined>(
    undefined,
  );
  const [optimisticMessage, setOptimisticMessage] = useState<ChatMessageType | null>(null);
  const [optimisticMessageIds, setOptimisticMessageIds] = useState<Set<string>>(new Set());
  const [messageMap, setMessageMap] = useState<Map<string, ChatMessageType>>(new Map());
  const [editedMessagesMap, setEditedMessagesMap] = useState<Map<string, {
    session: string, 
    id: string, 
    edit: boolean,
    content: string,
    original_content?: string,
    is_optimistic_edited?: boolean
  }>>(new Map());
  const [isNewSession, setIsNewSession] = useState<boolean>(
    !visibleSession || visibleSession === ""
  );
  const [isPending, startTransition] = useTransition();
  const [stableDisplayHistory, setStableDisplayHistory] = useState<ChatMessageType[]>([]);
  const messages = useMessagesStore((state) => state.messages);
  const nodes = useFlowStore((state) => state.nodes);
  const chatInput = inputs.find((input) => input.type === "ChatInput");
  const chatInputNode = nodes.find((node) => node.id === chatInput?.id);
  const displayLoadingMessage = useMessagesStore(
    (state) => state.displayLoadingMessage,
  );

  const isBuilding = useFlowStore((state) => state.isBuilding);

  const inputTypes = inputs.map((obj) => obj.type);
  const updateFlowPool = useFlowStore((state) => state.updateFlowPool);
  const setChatValueStore = useUtilityStore((state) => state.setChatValueStore);
  const chatValueStore = useUtilityStore((state) => state.chatValueStore);
  const isTabHidden = useTabVisibility();

  // Enhanced logic to track edited message IDs
  const [editedMessageIds, setEditedMessageIds] = useState<Set<string>>(new Set());

  // Load edited messages from localStorage on component mount
  useEffect(() => {
    try {
      const storedEditedMessages = localStorage.getItem(EDITED_MESSAGES_STORAGE_KEY);
      if (storedEditedMessages) {
        const parsedData = JSON.parse(storedEditedMessages);
        // Fix type issue by properly converting the parsed data to the expected format
        const newMap = new Map<string, {
          session: string, 
          id: string, 
          edit: boolean, 
          content: string, 
          original_content?: string,
          is_optimistic_edited?: boolean
        }>();
        const editedIds = new Set<string>();
        
        // Iterate through the entries and ensure they have the correct structure
        Object.entries(parsedData).forEach(([key, value]) => {
          const typedValue = value as {
            session: string, 
            id: string, 
            edit: boolean, 
            content?: string, 
            original_content?: string,
            is_optimistic_edited?: boolean
          };
          if (typedValue && typeof typedValue === 'object' && 
              'session' in typedValue && 'id' in typedValue && 'edit' in typedValue) {
            
            // Handle case where old format didn't include content
            const content = typedValue.content || key.split('-').slice(1).join('-');
            
            newMap.set(key, {
              session: typedValue.session,
              id: typedValue.id,
              edit: typedValue.edit,
              content: content, // Ensure this is never undefined
              original_content: typedValue.original_content,
              is_optimistic_edited: typedValue.is_optimistic_edited || false
            });
            
            // Track edited message IDs
            if (typedValue.edit) {
              editedIds.add(typedValue.id);
            }
          }
        });
        
        setEditedMessagesMap(newMap);
        setEditedMessageIds(editedIds);
      }
    } catch (error) {
      console.error("Error loading edited messages from localStorage:", error);
    }
  }, []);

  // Save edited messages to localStorage whenever they change
  useEffect(() => {
    if (editedMessagesMap.size > 0) {
      try {
        const mapObject = Object.fromEntries(editedMessagesMap);
        localStorage.setItem(EDITED_MESSAGES_STORAGE_KEY, JSON.stringify(mapObject));
      } catch (error) {
        console.error("Error saving edited messages to localStorage:", error);
      }
    }
  }, [editedMessagesMap]);

  // Reset optimistic message state when changing sessions
  useEffect(() => {
    // When session changes, clear the optimistic message
    setOptimisticMessage(null);
    
    // Also clear the message map for messages that don't belong to this session
    setMessageMap(prev => {
      // Keep only messages that belong to the current session
      const newMap = new Map();
      
      prev.forEach((msg, id) => {
        if (msg.session === visibleSession) {
          // If we're keeping this message, make sure it's not optimistic if edited
          if (msg.edit) {
            newMap.set(id, {...msg, is_optimistic: false});
          } else {
            newMap.set(id, msg);
          }
        }
      });
      
      return newMap;
    });
  }, [visibleSession]);

  // Add a visibility handler to clean up optimistic messages when returning from another tab
  useEffect(() => {
    // When tab becomes visible again, clean up any stale optimistic messages
    if (!isTabHidden) {
      // Get all backend messages for current session
      const sessionMessages = messages.filter(msg => 
        msg.flow_id === currentFlowId && 
        (msg.session_id === visibleSession || (!msg.session_id && !visibleSession))
      );
      
      // Check if we have any backend messages with the same content as optimistic ones
      if (sessionMessages.length > 0) {
        const backendTexts = new Set(sessionMessages.map(msg => msg.text));
        
        // Find optimistic messages that now have backend counterparts
        const idsToRemove: string[] = [];
        
        messageMap.forEach((msg, id) => {
          if (msg.is_optimistic && backendTexts.has(msg.message as string)) {
            idsToRemove.push(id);
          }
        });
        
        // If we found any, clean them up
        if (idsToRemove.length > 0) {
          setMessageMap(prev => {
            const newMap = new Map(prev);
            idsToRemove.forEach(id => newMap.delete(id));
            return newMap;
          });
          
          // Also clear the optimistic message state if needed
          if (optimisticMessage && idsToRemove.includes(optimisticMessage.id)) {
            setOptimisticMessage(null);
          }
        }
      }
    }
  }, [isTabHidden, messages, currentFlowId, visibleSession, messageMap, optimisticMessage]);

  // Update isNewSession when visibleSession changes
  useEffect(() => {
    setIsNewSession(!visibleSession || visibleSession === "");
  }, [visibleSession]);

  // Update isNewSession when we receive backend messages
  useEffect(() => {
    if (messages.some(msg => 
        msg.flow_id === currentFlowId && 
        (msg.session_id === visibleSession || (!msg.session_id && !visibleSession))
    )) {
      setIsNewSession(false);
    }
  }, [messages, currentFlowId, visibleSession]);

  //build chat history
  useEffect(() => {
    const messagesFromMessagesStore: ChatMessageType[] = messages
      .filter(
        (message) => {
          // Basic filtering - must be from current flow and session
          const isCurrentFlow = message.flow_id === currentFlowId;
          
          // For new sessions or undefined sessions, be more permissive
          const isNewOrEmptySession = !visibleSession || visibleSession === "";
          
          // Check if message belongs to current session
          const isCurrentSession = visibleSession === message.session_id || visibleSession === null;
          
          if (!isCurrentFlow || !isCurrentSession) return false;
          
          // For User messages, check if we have a matching optimistic message
          if (message.sender === "User") {
            // First check if we have a direct clientMessageId match
            if (message.clientMessageId) {
              const optMsg = Array.from(messageMap.values()).find(m => m.id === message.clientMessageId);
              if (optMsg) {
                console.log("Found direct match with clientMessageId:", message.clientMessageId);
                
                // Update the messageMap entry with backend data but keep it optimistic for new sessions
                setMessageMap(prev => {
                  const newMap = new Map(prev);
                  
                  // Check if this is the first message in a new session
                  const isFirstMessageInNewSession = 
                    prev.size === 1 && 
                    Array.from(prev.values()).every(m => m.is_optimistic) ||
                    !visibleSession;
                  
                  // Keep the original message but add backend data to it
                  newMap.set(optMsg.id, {
                    ...optMsg,
                    backend_message_id: message.id,
                    backend_text: message.text,
                    backend_data: message,
                    // For the first message in a new session, keep it optimistic
                    // For other messages, MAINTAIN the existing is_optimistic flag to prevent flickering
                    is_optimistic: optMsg.is_optimistic 
                  });
                  return newMap;
                });
                
                return false; // Skip adding the backend message since we updated the optimistic one
              }
            }
            
            // Fallback to content and timestamp matching for backward compatibility
            let foundMatch = false;
            messageMap.forEach((optMsg, optId) => {
              if (optMsg.is_optimistic && 
                  optMsg.isSend && 
                  optMsg.message === message.text &&
                  Math.abs(new Date(optMsg.timestamp).getTime() - new Date(message.timestamp).getTime()) < 5000) {
                
                // Found a match - update the optimistic message with backend data
                console.log("Updating optimistic message with backend data:", message.id);
                
                // Update the messageMap entry with backend data but keep it optimistic for new sessions
                setMessageMap(prev => {
                  const newMap = new Map(prev);
                  
                  // Check if this is the first message in a new session
                  const isFirstMessageInNewSession = 
                    prev.size === 1 && 
                    Array.from(prev.values()).every(m => m.is_optimistic) ||
                    !visibleSession;
                  
                  newMap.set(optId, {
                    ...optMsg,
                    backend_message_id: message.id,
                    backend_text: message.text,
                    backend_data: message,
                    // Maintain the current optimistic flag to prevent UI flickering
                    is_optimistic: optMsg.is_optimistic
                  });
                  return newMap;
                });
                
                foundMatch = true;
              }
            });
            
            // If we found and updated a matching optimistic message, don't add the backend version
            return !foundMatch;
          }
          
          // For all other messages (like AI responses), always include them
          return true;
        }
      )
      .map((message) => {
        let files = message.files;
        if (Array.isArray(files)) {
          // files is already an array, no need to parse
        } else if (files === "[]" || files === "") {
          files = [];
        } else if (typeof files === "string") {
          try {
            files = JSON.parse(files);
          } catch (error) {
            console.error("Error parsing files:", error);
            files = [];
          }
        }
        
        // Check if this message has been edited according to our persistent map
        const messageText = message.text;
        const contentKey = `${message.sender === 'User' ? 'user' : 'ai'}-${messageText}`;
        const persistedEditInfo = editedMessagesMap.get(contentKey);
        
        // Update the enhanced check for edited messages
        let isEdited = message.edit || false;
        let updatedContent = messageText; // Default to original content
        
        // Check if this message or a similar one was edited in any session
        editedMessagesMap.forEach((editInfo, key) => {
          // For user messages, check using message content and sender type
          if (message.sender === 'User' && key.startsWith('user-')) {
            // For edited user messages, we need to compare the content
            // The message text will be different after edit, so we need to check by ID
            if (editInfo.id === message.id || 
                (editInfo.session === message.session_id && key.includes(messageText))) {
              isEdited = true;
              updatedContent = editInfo.content; // Use the edited content
            }
          } 
          // For AI messages, check by both content and ID
          else if (message.sender === 'Machine' && key.startsWith('ai-')) {
            if (editInfo.id === message.id || 
                (editInfo.session === message.session_id && key.includes(messageText))) {
              isEdited = true;
              updatedContent = editInfo.content; // Use the edited content
            }
          }
        });
        
        return {
          isSend: message.sender === "User",
          message: isEdited ? updatedContent : message.text, // Use updated content if edited
          sender_name: message.sender_name,
          files: files,
          id: message.id,
          timestamp: message.timestamp,
          session: message.session_id,
          // Apply edit flag from both message and our persisted edit map
          edit: isEdited,
          background_color: message.background_color || "",
          text_color: message.text_color || "",
          content_blocks: message.content_blocks || [],
          category: message.category || "",
          properties: message.properties || {},
          backend_message_id: message.id,
          backend_text: message.text,
          backend_data: message,
          is_optimistic: false // Messages from backend are not optimistic
        };
      });

    const finalChatHistory = [...messagesFromMessagesStore].sort((a, b) => {
      if (standardizeTimestamp) {
        const timestampA = standardizeTimestamp(a.timestamp);
        const timestampB = standardizeTimestamp(b.timestamp);
        return new Date(timestampA).getTime() - new Date(timestampB).getTime();
      }
      return new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime();
    });

    if (messages.length === 0 && !isBuilding && chatInputNode && isTabHidden) {
      setChatValueStore(
        chatInputNode.data.node.template["input_value"].value ?? "",
      );
    } else {
      isTabHidden ? setChatValueStore("") : null;
    }

    // When data is re-fetched, clean up any old optimistic messages that are now in the backend
    // This is important for when a user returns from a different tab/session
    if (messagesFromMessagesStore.length > 0) {
      // Get all message text content from backed messages with their edit status
      const backendMessages = messagesFromMessagesStore.map(msg => ({
        text: typeof msg.message === 'string' ? msg.message : JSON.stringify(msg.message),
        id: msg.id,
        edit: msg.edit,
        isSend: msg.isSend
      }));
      
      // Check for duplicate messages in messageMap
      const idsToRemove: string[] = [];
      
      messageMap.forEach((optMsg, optId) => {
        const messageContent = typeof optMsg.message === 'string' 
          ? optMsg.message 
          : JSON.stringify(optMsg.message);
          
        // Find matching backend messages
        const matchingBackendMessage = backendMessages.find(backendMsg => 
          backendMsg.text === messageContent && 
          backendMsg.isSend === optMsg.isSend
        );
          
        // If this is an optimistic message that now exists in the backend, clean it up
        if (matchingBackendMessage) {
          // For edited messages, check both maps to ensure edit status is maintained
          if (optMsg.edit) {
            // Create a content key for the edited messages map
            const contentKey = `${optMsg.isSend ? 'user' : 'ai'}-${messageContent}`;
            
            // Save the edit status in our persistent map before removing it
            setEditedMessagesMap(prev => {
              const newMap = new Map(prev);
              newMap.set(contentKey, {
                session: optMsg.session || visibleSession || "",
                id: matchingBackendMessage.id,
                edit: true,
                content: messageContent
              });
              return newMap;
            });
          }
          
          // Mark for removal if it's not a current optimistic message (has is_optimistic=false)
          if (!optMsg.is_optimistic || optMsg.edit) {
            console.log("Found duplicate message to remove:", optId);
            idsToRemove.push(optId);
          }
        }
      });
      
      // If we found messages to remove, update the messageMap
      if (idsToRemove.length > 0) {
        console.log("Cleaning up duplicate optimistic messages:", idsToRemove.length);
        setMessageMap(prev => {
          const newMap = new Map(prev);
          idsToRemove.forEach(id => newMap.delete(id));
          return newMap;
        });
        
        // Also clear the optimistic message if it's one being removed
        if (optimisticMessage && idsToRemove.includes(optimisticMessage.id)) {
          setOptimisticMessage(null);
        }
      }
    }

    // Add optimistic messages to history, avoiding duplicates
    const persistedHistory = [...finalChatHistory];
    
    // Keep track of message content we already have in history
    const existingMessageContents = new Set(
      persistedHistory.map(msg => typeof msg.message === 'string' ? msg.message : JSON.stringify(msg.message))
    );
    
    // For a new session, always prioritize adding optimistic messages
    const isNewSession = messagesFromMessagesStore.length === 0;
    
    // Keep track of which optimistic messages we've already added
    const addedOptimisticIds = new Set<string>();
    
    // Add optimistic messages that don't have a matching content in backend messages
    messageMap.forEach((message) => {
      const messageContent = typeof message.message === 'string' ? message.message : JSON.stringify(message.message);
      
      // For new sessions, always add the optimistic message, but avoid duplicates
      if (isNewSession) {
        // In new sessions, we need to check if we already added an optimistic message with the same content
        const hasDuplicate = persistedHistory.some(existingMsg => 
          existingMsg.is_optimistic && 
          (typeof existingMsg.message === 'string' ? existingMsg.message : JSON.stringify(existingMsg.message)) === messageContent
        );
        
        if (!hasDuplicate) {
          persistedHistory.push(message);
          addedOptimisticIds.add(message.id);
        }
      }
      // For existing sessions, only add if not already present
      else if (!existingMessageContents.has(messageContent)) {
        persistedHistory.push(message);
      }
    });

    setChatHistory(persistedHistory);
  }, [flowPool, messages, visibleSession, standardizeTimestamp, messageMap]);
  
  // Scroll to bottom whenever chat history updates or when messageMap changes
  useEffect(() => {
    if (messagesRef.current) {
      messagesRef.current.scrollTop = messagesRef.current.scrollHeight;
    }
  }, [chatHistory, messageMap.size]);

  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (ref.current) {
      ref.current.focus();
    }
    // trigger focus on chat when new session is set
  }, [focusChat]);

  const { files, setFiles, handleFiles } = useFileHandler(currentFlowId);
  const [isDragging, setIsDragging] = useState(false);

  const { dragOver, dragEnter, dragLeave } = useDragAndDrop(setIsDragging);

  const onDrop = (e) => {
    e.preventDefault();
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFiles(e.dataTransfer.files);
      e.dataTransfer.clearData();
    }
    setIsDragging(false);
  };

  const flowRunningSkeletonMemo = useMemo(() => <FlowRunningSqueleton />, []);

  // Update the displayChatHistory logic to properly deduplicate edited messages
  const displayChatHistory = useMemo(() => {
    if (!chatHistory) return [];
    
    // Only show messages from the current session
    const sessionMessages = chatHistory.filter(msg => 
      msg.session === visibleSession || 
      (visibleSession === currentFlowId && !msg.session) ||
      // For new sessions, include messages with empty session ID
      (!visibleSession && !msg.session)
    );
    
    // IMPORTANT: For duplicate detection, we need to track conversation turns
    // If there's an AI message between two user messages, they should be considered separate turns
    
    // First, sort messages by timestamp
    const sortedMessages = [...sessionMessages].sort((a, b) => {
      const timestampA = standardizeTimestamp ? standardizeTimestamp(a.timestamp) : a.timestamp;
      const timestampB = standardizeTimestamp ? standardizeTimestamp(b.timestamp) : b.timestamp;
      return new Date(timestampA).getTime() - new Date(timestampB).getTime();
    });
    
    // Process messages to maintain conversation turns and optimize display
    const result: ChatMessageType[] = [];
    
    // To track optimistic user messages that need backend data
    const pendingOptimisticMessages = new Map<string, number>(); // content -> index in result
    
    // Process chronologically to preserve conversation flow
    for (let i = 0; i < sortedMessages.length; i++) {
      const msg = sortedMessages[i];
      const isUserMessage = msg.isSend;
      const messageContent = typeof msg.message === 'string' ? msg.message : JSON.stringify(msg.message);
      
      // Try to find a recent optimistic version of this message to update
      if (!msg.is_optimistic && isUserMessage && pendingOptimisticMessages.has(messageContent)) {
        const optimisticIndex = pendingOptimisticMessages.get(messageContent)!;
        // Update the optimistic message with backend data
        result[optimisticIndex] = {
          ...result[optimisticIndex],
          backend_message_id: msg.id,
          backend_text: messageContent,
          backend_data: msg,
          // Keep is_optimistic true to prevent UI flicker
        };
        // Continue to next message without adding this one
        continue;
      }
      
      // Check if this is a duplicate of the last user message with no AI response in between
      let isDuplicate = false;
      if (isUserMessage && result.length > 0) {
        // Find the last user message in the result
        let lastUserMsgIndex = -1;
        for (let j = result.length - 1; j >= 0; j--) {
          if (result[j].isSend) {
            lastUserMsgIndex = j;
            break;
          }
        }
        
        // If we found a previous user message
        if (lastUserMsgIndex >= 0) {
          const lastUserMsg = result[lastUserMsgIndex];
          const lastUserContent = typeof lastUserMsg.message === 'string' ? lastUserMsg.message : JSON.stringify(lastUserMsg.message);
          
          // Check if it has the same content and no AI messages between them
          if (lastUserContent === messageContent) {
            // Check if there was an AI message between these two user messages
            const hasAiMessageBetween = result.slice(lastUserMsgIndex + 1).some(m => !m.isSend);
            
            // If no AI messages between and messages are close in time, it's likely a duplicate
            if (!hasAiMessageBetween && 
                Math.abs(new Date(lastUserMsg.timestamp).getTime() - new Date(msg.timestamp).getTime()) < 5000) {
              
              // If the new message is not optimistic and the existing one is, update it
              if (!msg.is_optimistic && lastUserMsg.is_optimistic) {
                result[lastUserMsgIndex] = {
                  ...lastUserMsg,
                  backend_message_id: msg.id,
                  backend_text: messageContent,
                  backend_data: msg,
                  // Keep is_optimistic true to prevent UI flicker
                };
                isDuplicate = true;
              }
              // If the new message is optimistic and the existing isn't, replace with optimistic
              else if (msg.is_optimistic && !lastUserMsg.is_optimistic) {
                result[lastUserMsgIndex] = {
                  ...msg,
                  backend_message_id: lastUserMsg.id,
                  backend_text: lastUserContent,
                  backend_data: lastUserMsg,
                };
                isDuplicate = true;
              }
              // If both are optimistic or both are not, keep the more recent one
              else if ((msg.is_optimistic && lastUserMsg.is_optimistic) || 
                      (!msg.is_optimistic && !lastUserMsg.is_optimistic)) {
                if (new Date(msg.timestamp) > new Date(lastUserMsg.timestamp)) {
                  result[lastUserMsgIndex] = msg;
                }
                isDuplicate = true;
              }
            }
          }
        }
      }
      
      // If it's not a duplicate, add it to the result
      if (!isDuplicate) {
        result.push(msg);
        
        // If it's an optimistic user message, track it for potential backend updates
        if (msg.is_optimistic && isUserMessage) {
          pendingOptimisticMessages.set(messageContent, result.length - 1);
        }
      }
    }
    
    return result;
  }, [chatHistory, visibleSession, currentFlowId, standardizeTimestamp]);

  // Use useTransition to update the display history smoothly
  useEffect(() => {
    if (displayChatHistory) {
      startTransition(() => {
        setStableDisplayHistory(displayChatHistory);
      });
    }
  }, [displayChatHistory]);

  // Create a stable array of keys for the chat messages to prevent unnecessary re-renders
  const chatMessageKeys = useMemo(() => {
    // Use a combination of ID and content to create stable keys
    // This helps preserve component identity even when messages are updated
    return stableDisplayHistory.map(chat => {
      const contentKey = typeof chat.message === 'string' 
        ? chat.message.substring(0, 20) // Use first 20 chars of message as part of key
        : JSON.stringify(chat.message).substring(0, 20);
      return `${chat.id}-${chat.is_optimistic ? 'opt' : 'reg'}-${contentKey}`;
    });
  }, [stableDisplayHistory]);

  // Memoize the updateChat function to maintain reference stability
  const updateChatMemoized = useCallback((
    chat: ChatMessageType,
    message: string,
    stream_url?: string,
  ) => {
    console.log("Updating chat message:", {
      id: chat.id,
      oldMessage: chat.message,
      newMessage: message
    });
    
    // Update the message locally
    chat.message = message;
    
    // Mark as edited
    chat.edit = true;
    
    // Track this ID as edited to help with deduplication
    setEditedMessageIds(prev => {
      const newSet = new Set(prev);
      newSet.add(chat.id);
      return newSet;
    });
    
    // Add to editedMessagesMap to persist edit status across session switches
    if (chat.id) {
      // Create a content key to help with tracking edits
      const contentKey = `${chat.isSend ? 'user' : 'ai'}-${message}`;
      
      // Get the original content with proper type handling
      const originalContent = typeof chat.backend_text === 'string' 
        ? chat.backend_text 
        : (typeof chat.message === 'string' 
            ? chat.message 
            : JSON.stringify(chat.message));
      
      // Update the edited messages map
      setEditedMessagesMap(prev => {
        const newMap = new Map(prev);
        newMap.set(contentKey, {
          session: chat.session || visibleSession || "",
          id: chat.id,
          edit: true,
          content: message,
          original_content: originalContent, // Use properly typed original content
          is_optimistic_edited: chat.is_optimistic || false // Track if this was an optimistic message
        });
        return newMap;
      });
    }
    
    // If this is a message tracked in messageMap, update it there too
    if (chat.id) {
      setMessageMap(prev => {
        // Check if we're tracking this message
        if (prev.has(chat.id)) {
          const newMap = new Map(prev);
          const currentMsg = newMap.get(chat.id);
          
          // Create updated message with edit flag and add metadata to help with cleaning up duplicates
          const updatedMsg = {
            ...currentMsg!,
            message: message,
            edit: true,
            // Explicitly set is_optimistic to false to indicate this has been fully processed
            is_optimistic: false
          };
          
          // Update the message
          newMap.set(chat.id, updatedMsg);
          return newMap;
        }
        return prev;
      });
    }
    
    // Also update chatHistory to ensure the UI updates immediately
    setChatHistory(prev => {
      if (!prev) return prev;
      
      // Create a new array to trigger a re-render
      return prev.map(msg => {
        if (msg.id === chat.id) {
          // Return a new object with updated message and edit flag
          return {
            ...msg,
            message: message,
            edit: true,
            is_optimistic: false // Ensure edited messages are no longer optimistic
          };
        }
        return msg;
      });
    });
    
    // If this was the optimistic message, clear it to avoid duplication
    if (optimisticMessage && optimisticMessage.id === chat.id) {
      setOptimisticMessage(null);
    }
    
    // Clear any optimistic messages with matching content to avoid duplicates after saving an edit
    setMessageMap(prev => {
      const newMap = new Map(prev);
      // Find any optimistic message with the same content or same ID
      prev.forEach((msg, id) => {
        if (msg.is_optimistic && 
           (msg.message === message || 
            msg.id === chat.id ||
            msg.backend_message_id === chat.backend_message_id)) {
          newMap.delete(id);
        }
      });
      return newMap;
    });
    
    // Update flow pool if needed
    if (chat.componentId) {
      updateFlowPool(chat.componentId, {
        message,
        sender_name: chat.sender_name ?? "Bot",
        sender: chat.isSend ? "User" : "Machine",
      });
    }
  }, [updateFlowPool, setEditedMessagesMap, visibleSession, setMessageMap, setChatHistory, setEditedMessageIds, optimisticMessage]);

  // When this component is mounted, check for any edited messages in localStorage
  useEffect(() => {
    // For edited messages in the current session, apply the edit status to messageMap
    if (editedMessagesMap.size > 0 && messageMap.size > 0) {
      setMessageMap(prev => {
        const newMap = new Map(prev);
        
        // Loop through messageMap and check if any messages have an edit state
        newMap.forEach((msg, id) => {
          // Create a content key to check editedMessagesMap
          const messageContent = typeof msg.message === 'string' 
            ? msg.message 
            : JSON.stringify(msg.message);
          const contentKey = `${msg.isSend ? 'user' : 'ai'}-${messageContent}`;
          
          // Check if this message or one with this content was edited
          editedMessagesMap.forEach((editInfo, editKey) => {
            // For user messages, check if this is their ID or content
            if (msg.isSend && editKey.startsWith('user-')) {
              if (editInfo.id === msg.id || 
                  (editInfo.session === msg.session && editKey.includes(messageContent))) {
                // Apply the edit flag and update content
                newMap.set(id, {...msg, edit: true, message: editInfo.content});
              }
            }
            // For AI messages, similar logic
            else if (!msg.isSend && editKey.startsWith('ai-')) {
              if (editInfo.id === msg.id || 
                  (editInfo.session === msg.session && editKey.includes(messageContent))) {
                // Apply the edit flag and update content
                newMap.set(id, {...msg, edit: true, message: editInfo.content});
              }
            }
          });
        });
        
        return newMap;
      });
    }
  }, [editedMessagesMap, messageMap.size, visibleSession]);

  // Ensure optimistic messages are always displayed immediately
  useEffect(() => {
    // When a new optimistic message is added to messageMap, update chatHistory immediately
    const optimisticMessages = Array.from(messageMap.values()).filter(msg => 
      msg.is_optimistic && 
      !editedMessageIds.has(msg.id) && 
      msg.session === visibleSession
    );
    
    if (optimisticMessages.length > 0) {
      // Add these to chat history if they don't exist already
      setChatHistory(prev => {
        if (!prev) return optimisticMessages;
        
        const existingIds = new Set(prev.map(msg => msg.id));
        const newMessages = optimisticMessages.filter(msg => !existingIds.has(msg.id));
        
        if (newMessages.length === 0) return prev;
        
        return [...prev, ...newMessages];
      });
    }
  }, [messageMap, visibleSession, editedMessageIds]);

  return (
    <div
      className="flex h-full w-full flex-col rounded-md pb-2"
      onDragOver={dragOver}
      onDragEnter={dragEnter}
      onDragLeave={dragLeave}
      onDrop={onDrop}
    >
      <div ref={messagesRef} className="chat-message-div pb-10">
        {/* First check if we have an optimistic message but no chat history */}
        {optimisticMessage && (!chatHistory || chatHistory.length === 0) && !editedMessageIds.has(optimisticMessage.id) ? (
          <MemoizedChatMessage
            chat={optimisticMessage}
            lastMessage={true}
            key={optimisticMessage.id}
            updateChat={updateChatMemoized}
            closeChat={closeChat}
          />
        ) : /* Check if we have optimistic messages in a new session that should be displayed */
        chatHistory && messageMap.size > 0 && Array.from(messageMap.values()).some(m => m.is_optimistic) && displayChatHistory?.length === 0 ? (
          // Special case: We have optimistic messages but they're not in displayChatHistory yet
          <>
            {Array.from(messageMap.values())
              .filter(m => m.is_optimistic && !editedMessageIds.has(m.id)) // Skip edited optimistic messages
              .sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime())
              .map((chat, index, arr) => (
                <MemoizedChatMessage
                  chat={chat}
                  lastMessage={arr.length - 1 === index}
                  key={chat.id}
                  updateChat={updateChatMemoized}
                  closeChat={closeChat}
                />
              ))}
          </>
        ) : chatHistory &&
          (isBuilding || stableDisplayHistory?.length > 0 ? (
            <>
              {stableDisplayHistory?.map((chat, index) => (
                <MemoizedChatMessage
                  chat={chat}
                  lastMessage={stableDisplayHistory.length - 1 === index}
                  key={chatMessageKeys[index]}
                  updateChat={updateChatMemoized}
                  closeChat={closeChat}
                />
              ))}
            </>
          ) : (
            <div className="flex h-full w-full flex-col items-center justify-center">
              <div className="flex flex-col items-center justify-center gap-4 p-8">
                {ENABLE_NEW_LOGO ? (
                  <LangflowLogo
                    title="Langflow logo"
                    className="h-10 w-10 scale-[1.5]"
                  />
                ) : (
                  <ChainLogo
                    title="Langflow logo"
                    className="h-10 w-10 scale-[1.5]"
                  />
                )}
                <div className="flex flex-col items-center justify-center">
                  <h3 className="mt-2 pb-2 text-2xl font-semibold text-primary">
                    New chat
                  </h3>
                  <p
                    className="text-lg text-muted-foreground"
                    data-testid="new-chat-text"
                  >
                    <TextEffectPerChar>
                      Test your flow with a chat prompt
                    </TextEffectPerChar>
                  </p>
                </div>
              </div>
            </div>
          ))}
        <div
          className={
            displayLoadingMessage
              ? "w-full max-w-[768px] py-4 word-break-break-word md:w-5/6"
              : ""
          }
          ref={ref}
        >
          {displayLoadingMessage &&
            !(stableDisplayHistory?.[stableDisplayHistory.length - 1]?.category === "error") &&
            flowRunningSkeletonMemo}
        </div>
      </div>
      <div className="m-auto w-full max-w-[768px] md:w-5/6">
        <ChatInput
          noInput={!inputTypes.includes("ChatInput")}
          sendMessage={({ repeat, files }) => {
            // Use a timestamp format that matches the server (YYYY-MM-DD HH:MM:SS UTC)
            const now = new Date();
            const formattedDate = now.toISOString()
              .replace('T', ' ')
              .replace(/\.\d+Z$/, ' UTC');
            
            // Generate a proper UUID that the backend will accept
            const messageId = uuidv4();
            
            // Create optimistic message
            const optimistic: ChatMessageType = {
              isSend: true,
              message: chatValueStore,
              sender_name: "User",
              files: files || [],
              id: messageId,
              timestamp: formattedDate,
              session: visibleSession || "",
              edit: false,
              content_blocks: [],
              category: "",
              properties: { 
                source: {
                  id: "user", 
                  display_name: "User", 
                  source: "user"
                },
                background_color: "",
                text_color: "",
              },
              is_optimistic: true // Explicitly mark as optimistic
            };
            
            // Add the message ID to our tracking set
            setOptimisticMessageIds(prev => {
              const newSet = new Set(prev);
              newSet.add(messageId);
              return newSet;
            });
            
            // Log the current state
            console.log("Is new session (state):", isNewSession);
            
            // Add the message to our persistent map
            setMessageMap(prev => {
              const newMap = new Map(prev);
              newMap.set(messageId, optimistic);
              return newMap;
            });
            
            // For ALL messages, update the chat history directly
            // This ensures the optimistic message appears immediately
            // First force create an empty history if none exists
            if (!chatHistory) {
              setChatHistory([]);
            }
            
            // Then add the optimistic message
            setChatHistory(prev => {
              const newHistory = prev ? [...prev] : [];
              // Only add if not already present to avoid duplicates
              const isDuplicate = newHistory.some(msg => 
                msg.is_optimistic && msg.id === optimistic.id
              );
              
              if (!isDuplicate) {
                console.log("Adding optimistic message to chat history");
                newHistory.push(optimistic);
              }
              return newHistory;
            });
            
            // Always update the optimistic message reference for consistent display
            setOptimisticMessage(optimistic);
            
            // Clear input immediately to improve responsiveness
            setChatValueStore("");
            
            // Send actual message to backend with client messageId
            sendMessage({ 
              repeat, 
              files: files || [], 
              clientMessageId: messageId // Include client ID
            });
            
            track("Playground Message Sent");
          }}
          inputRef={ref}
          files={files}
          setFiles={setFiles}
          isDragging={isDragging}
        />
      </div>
    </div>
  );
}


