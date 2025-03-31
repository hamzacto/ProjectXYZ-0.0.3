import { ProfileIcon } from "@/components/core/appHeaderComponent/components/ProfileIcon";
import { ContentBlockDisplay } from "@/components/core/chatComponents/ContentBlockDisplay";
import { useUpdateMessage } from "@/controllers/API/queries/messages";
import { CustomProfileIcon } from "@/customization/components/custom-profile-icon";
import { ENABLE_DATASTAX_LANGFLOW } from "@/customization/feature-flags";
import useFlowsManagerStore from "@/stores/flowsManagerStore";
import useFlowStore from "@/stores/flowStore";
import { useUtilityStore } from "@/stores/utilityStore";
import { ChatMessageType } from "@/types/chat";
import Convert from "ansi-to-html";
import { memo, useCallback, useEffect, useRef, useState, useMemo } from "react";
import Robot from "../../../../../assets/robot.png";
import IconComponent, {
  ForwardedIconComponent,
} from "../../../../../components/common/genericIconComponent";
import SanitizedHTMLWrapper from "../../../../../components/common/sanitizedHTMLWrapper";
import { Card } from "../../../../../components/ui/card";
import { EMPTY_INPUT_SEND_MESSAGE } from "../../../../../constants/constants";
import useTabVisibility from "../../../../../shared/hooks/use-tab-visibility";
import useAlertStore from "../../../../../stores/alertStore";
import { useDarkStore } from "../../../../../stores/darkStore";
import { chatMessagePropsType } from "../../../../../types/components";
import { cn } from "../../../../../utils/utils";
import { ErrorView } from "./components/content-view";
import { MarkdownField } from "./components/edit-message";
import EditMessageField from "./components/edit-message-field";
import FileCardWrapper from "./components/file-card-wrapper";
import { EditMessageButton } from "./components/message-options";
import { convertFiles } from "./helpers/convert-files";
import { api } from "../../../../../controllers/API/api";
import { getURL } from "../../../../../controllers/API/helpers/constants";

// Main function wrapped in memo for consistent reference identity
const ChatMessage = ({
  chat,
  lastMessage,
  updateChat,
  closeChat,
  flowIcon,
}: chatMessagePropsType): JSX.Element => {
  const convert = new Convert({ newline: true });
  const [hidden, setHidden] = useState(true);
  const [streamUrl, setStreamUrl] = useState(chat.stream_url);
  const flow_id = useFlowsManagerStore((state) => state.currentFlowId);
  const currentFlow = useFlowsManagerStore((state) => state.currentFlow);
  const fitViewNode = useFlowStore((state) => state.fitViewNode);

  // Preserve message identity for user messages to prevent flickering
  const initialMessage = useRef(chat.message ? chat.message.toString() : "");
  const isUserMessage = chat.isSend;

  // We need to check if message is not undefined because
  // we need to run .toString() on it
  const [chatMessage, setChatMessage] = useState(initialMessage.current);
  const [isStreaming, setIsStreaming] = useState(false);
  const eventSource = useRef<EventSource | undefined>(undefined);
  const setErrorData = useAlertStore((state) => state.setErrorData);
  const chatMessageRef = useRef(chatMessage);
  const [editMessage, setEditMessage] = useState(false);
  const [showError, setShowError] = useState(false);
  const isBuilding = useFlowStore((state) => state.isBuilding);
  const dark = useDarkStore((state) => state.dark);
  
  // Get the utility store functions to control auto-scrolling
  const setDisableAutoScroll = useUtilityStore((state) => state.setDisableAutoScroll);
  
  // When entering/exiting edit mode, control auto-scrolling
  useEffect(() => {
    // Disable auto-scrolling when entering edit mode
    if (editMessage) {
      setDisableAutoScroll(true);
    } else {
      // Re-enable auto-scrolling after a small delay when exiting edit mode
      // to ensure UI updates complete first
      setTimeout(() => {
        setDisableAutoScroll(false);
      }, 100);
    }
  }, [editMessage, setDisableAutoScroll]);
  
  // Only update message from props if it's not a user message 
  // (prevents flickering from backend updates to user messages)
  useEffect(() => {
    if (!isUserMessage) {
      const chatMessageString = chat.message ? chat.message.toString() : "";
      setChatMessage(chatMessageString);
      chatMessageRef.current = chatMessageString;
    }
  }, [chat, isBuilding, isUserMessage]);

  const playgroundScrollBehaves = useUtilityStore(
    (state) => state.playgroundScrollBehaves,
  );
  const setPlaygroundScrollBehaves = useUtilityStore(
    (state) => state.setPlaygroundScrollBehaves,
  );
  
  // Add a ref to track if user is actively scrolling - shared across all chat messages
  const isUserScrolling = useUtilityStore(
    (state) => state.isUserScrolling || false,
  );
  
  // Get/set the bottom visibility state from the store
  const isAtBottom = useUtilityStore(
    (state) => state.isAtBottomOfChat || true,
  );
  const setIsAtBottomOfChat = useUtilityStore(
    (state) => state.setIsAtBottomOfChat || (() => {}),
  );

  // The idea now is that chat.stream_url MAY be a URL if we should stream the output of the chat
  // probably the message is empty when we have a stream_url
  // what we need is to update the chat_message with the SSE data
  const streamChunks = useCallback((url: string) => {
    setIsStreaming(true); // Streaming starts
    return new Promise<boolean>((resolve, reject) => {
      eventSource.current = new EventSource(url);
      eventSource.current.onmessage = (event) => {
        let parsedData = JSON.parse(event.data);
        if (parsedData.chunk) {
          setChatMessage((prev) => prev + parsedData.chunk);
        }
      };
      eventSource.current.onerror = (event: any) => {
        setIsStreaming(false);
        eventSource.current?.close();
        setStreamUrl(undefined);
        if (JSON.parse(event.data)?.error) {
          setErrorData({
            title: "Error on Streaming",
            list: [JSON.parse(event.data)?.error],
          });
        }
        updateChat(chat, chatMessageRef.current);
        reject(new Error("Streaming failed"));
      };
      eventSource.current.addEventListener("close", (event) => {
        setStreamUrl(undefined); // Update state to reflect the stream is closed
        eventSource.current?.close();
        setIsStreaming(false);
        resolve(true);
      });
    });
  }, [chat, setErrorData, updateChat]);

  useEffect(() => {
    if (streamUrl && !isStreaming) {
      streamChunks(streamUrl)
        .then(() => {
          if (updateChat) {
            updateChat(chat, chatMessageRef.current);
          }
        })
        .catch((error) => {
          console.error(error);
        });
    }
  }, [streamUrl, chatMessage, streamChunks, updateChat]);
  
  useEffect(() => {
    return () => {
      eventSource.current?.close();
    };
  }, []);

  const isTabHidden = useTabVisibility();

  // Completely remove scroll-to-bottom behavior
  useEffect(() => {
    // No auto-scrolling functionality
    // Only keep the lastMessage marker for accessibility
    if (lastMessage) {
      const element = document.getElementById("last-chat-message");
      // No scrolling, just ensure the element has proper ID
    }
  }, [lastMessage]);

  useEffect(() => {
    if (chat.category === "error") {
      // Short delay before showing error to allow for loading animation
      const timer = setTimeout(() => {
        setShowError(true);
      }, 50);
      return () => clearTimeout(timer);
    }
  }, [chat.category]);

  let decodedMessage = chatMessage ?? "";
  try {
    decodedMessage = decodeURIComponent(chatMessage);
  } catch (e) {
    // console.error(e);
  }
  const isEmpty = decodedMessage?.trim() === "";
  const { mutate: updateMessageMutation } = useUpdateMessage();

  const handleEditMessage = (message: string) => {
    // Add more detailed logging
    console.log("Edit attempt for message:", {
      id: chat.id,
      hasBackendData: !!chat.backend_data,
      backend_id: chat.backend_message_id,
      message: chat.message,
      is_optimistic: chat.is_optimistic
    });

    // Check if this is an optimistic message that can't be edited yet
    if (chat.is_optimistic) {
      setErrorData({
        title: "Cannot edit yet",
        list: ["This message is still being processed by the server. Please wait a moment before editing."]
      });
      return;
    }

    // For user messages, make sure we have backend data
    if (chat.isSend && !chat.backend_data) {
      setErrorData({
        title: "Cannot edit message",
        list: ["This message doesn't have the necessary data for editing. Please try again later."]
      });
      return;
    }

    // Use backend data if available, otherwise fall back to chat data
    const backendData = chat.backend_data || chat;
    const messageId = chat.backend_message_id || chat.id;
    const sessionId = backendData.session_id || chat.session || "";
    
    console.log("Sending edit with:", {
      messageId,
      sessionId,
      text: message
    });
    
    updateMessageMutation(
      {
        message: {
          ...backendData,
          files: convertFiles(chat.files),
          sender_name: chat.sender_name ?? "AI",
          text: message,
          sender: chat.isSend ? "User" : "Machine",
          flow_id,
          session_id: sessionId,
          id: messageId
        },
        refetch: false,
      },
      {
        onSuccess: (data) => {
          console.log("Edit successful:", data);
          
          // Update the message locally in this component
          setChatMessage(message);
          chatMessageRef.current = message;
          
          // Update the chat locally without waiting for backend refresh
          updateChat(chat, message);
          
          // Mark this message as edited
          chat.edit = true;
          
          // Exit edit mode
          setEditMessage(false);
          
          // Force re-render to show edit flag immediately
          setForceUpdate(prev => !prev);
        },
        onError: (error) => {
          console.error("Error updating message:", error);
          const errorDetail = error?.response?.data?.detail || "Unknown error";
          setErrorData({
            title: "Error updating message",
            list: [errorDetail]
          });
        },
      },
    );
  };

  const handleEvaluateAnswer = (evaluation: boolean | null) => {
    // Use backend data if available, otherwise fall back to chat data
    const backendData = chat.backend_data || chat;
    const messageId = chat.backend_message_id || chat.id;
    const sessionId = backendData.session_id || chat.session || "";
    
    updateMessageMutation(
      {
        message: {
          ...backendData,
          files: convertFiles(chat.files),
          sender_name: chat.sender_name ?? "AI",
          text: chat.message.toString(),
          sender: chat.isSend ? "User" : "Machine",
          flow_id,
          session_id: sessionId,
          id: messageId,
          properties: {
            ...chat.properties,
            positive_feedback: evaluation,
          },
        },
        refetch: true,
      },
      {
        onError: () => {
          setErrorData({
            title: "Error updating messages.",
          });
        },
      },
    );
  };

  // Add forceUpdate state to trigger re-renders
  const [forceUpdate, setForceUpdate] = useState(false);

  // Use a memoized version of the edited flag that updates when edit status changes
  const editedFlag = useMemo(() => 
    chat.edit ? (
      <div className="text-sm text-muted-foreground" key={`edited-${chat.id}-${String(chat.edit)}-${forceUpdate}`}>
        (Edited)
      </div>
    ) : null
  , [chat.id, chat.edit, forceUpdate]);

  if (chat.category === "error") {
    const blocks = chat.content_blocks ?? [];

    return (
      <ErrorView
        blocks={blocks}
        showError={showError}
        lastMessage={lastMessage}
        closeChat={closeChat}
        fitViewNode={fitViewNode}
        chat={chat}
      />
    );
  }

  // Set background and text colors based on dark mode for user messages
  const backgroundColor = dark ? "#303030" : "#f3f3f3";
  const textColor = dark ? "white" : "black";

  return (
    <>
      {chat.isSend ? (
        // User message styled to match UserMessage.tsx
        <div className="w-5/6 max-w-[768px] py-6 word-break-break-word">
          <div className="flex justify-end w-full">
            <div className="relative group max-w-[80%]">
              {/* Extended hover area below the message */}
              <div className="absolute -bottom-10 left-0 right-0 h-12 z-10"></div>
              <Card 
                className={cn(
                  "w-full py-3 px-4 rounded-3xl shadow-none border-0 transition-none relative z-20",
                  editMessage ? "z-30 overflow-visible bg-background" : ""
                )}
                style={editMessage ? {} : { backgroundColor, color: textColor }}
              >
                {editMessage ? (
                  <div className="z-50">
                    <EditMessageField
                      key={`edit-message-${chat.id}`}
                      message={decodedMessage}
                      onEdit={(message) => {
                        handleEditMessage(message);
                      }}
                      onCancel={() => setEditMessage(false)}
                    />
                  </div>
                ) : (
                  <span className="whitespace-pre-wrap break-words text-[14px]" data-testid={`chat-message-${chat.sender_name}-${chatMessage}`}>
                    {isEmpty ? EMPTY_INPUT_SEND_MESSAGE : decodedMessage}
                    {editedFlag}
                  </span>
                )}
                {chat.files && chat.files.length > 0 && (
                  <div className="my-2 flex flex-col gap-5">
                    {chat.files?.map((file, index) => {
                      return <FileCardWrapper key={index} index={index} path={file} />;
                    })}
                  </div>
                )}
              </Card>
              {!editMessage && (
                <div className="invisible absolute -bottom-8 right-0 group-hover:visible opacity-0 group-hover:opacity-100 transition-opacity duration-200 z-10">
                  <div>
                    <EditMessageButton
                      onCopy={() => {
                        navigator.clipboard.writeText(chatMessage);
                      }}
                      onDelete={() => {}}
                      onEdit={() => setEditMessage(true)}
                      className="h-fit group-hover:visible"
                      isBotMessage={!chat.isSend}
                      onEvaluate={handleEvaluateAnswer}
                      evaluation={chat.properties?.positive_feedback}
                    />
                  </div>
                </div>
              )}
            </div>
          </div>
          <div id={lastMessage ? "last-chat-message" : undefined} />
        </div>
      ) : (
        // Original AI message implementation kept intact
        <div className="w-5/6 max-w-[768px] py-6 word-break-break-word">
          <div
            className={cn(
              "group relative flex w-full gap-4 rounded-md p-2",
              editMessage ? "" : "hover:bg-muted",
            )}
          >
            {/* Invisible extended hover area */}
            <div className="absolute inset-0 -bottom-10 z-0"></div>
            <div
              className={cn(
                "relative flex h-[50px] w-[50px] items-center justify-center overflow-hidden rounded-md text-2xl",
                "bg-muted"
              )}
              style={
                chat.properties?.background_color
                  ? { backgroundColor: chat.properties.background_color }
                  : {}
              }
            >
              <div className="flex h-[46px] w-[46px] items-center justify-center p-1">
                {chat.properties?.icon ? (
                  chat.properties.icon.match(
                    /[\u2600-\u27BF\uD83C-\uDBFF\uDC00-\uDFFF]/,
                  ) ? (
                    <span className="">{chat.properties.icon}</span>
                  ) : (
                    <ForwardedIconComponent name={flowIcon ?? "Avatar2"} className="w-10 h-10"/>
                  )
                ) : flowIcon ? (
                  // Use the flow icon if we fetched it successfully
                  <ForwardedIconComponent name={flowIcon ?? "Avatar2"} className="w-12 h-12"/>
                ) : (
                  // Fallback to robot image if no flow icon is available
                  <img
                    src={Robot}
                    className="absolute bottom-0 left-0 scale-[60%]"
                    alt={"robot_image"}
                  />
                )}
              </div>
            </div>
            <div className="flex w-[94%] flex-col">
              <div>
                <div
                  className={cn(
                    "flex max-w-full items-baseline gap-3 truncate pb-2 text-[14px] font-semibold",
                  )}
                  style={
                    chat.properties?.text_color
                      ? { color: chat.properties.text_color }
                      : {}
                  }
                  data-testid={
                    "sender_name_" + chat.sender_name?.toLocaleLowerCase()
                  }
                >
                  {currentFlow?.name && (
                        <span className="ml-1">{currentFlow.name}</span>
                      )}
                  {/* {chat.properties?.source && (
                    <div className="text-[13px] font-normal text-muted-foreground">
                      {chat.properties?.source.source}
                    </div>
                  )} */}
                </div>
              </div>
              {chat.content_blocks && chat.content_blocks.length > 0 && (
                <ContentBlockDisplay
                  contentBlocks={chat.content_blocks}
                  isLoading={
                    chatMessage === "" &&
                    chat.properties?.state === "partial" &&
                    isBuilding &&
                    lastMessage
                  }
                  state={chat.properties?.state}
                  chatId={chat.id}
                />
              )}
              <div className="form-modal-chat-text-position flex-grow">
                <div className="form-modal-chat-text">
                  {hidden && chat.thought && chat.thought !== "" && (
                    <div
                      onClick={(): void => setHidden((prev) => !prev)}
                      className="form-modal-chat-icon-div"
                    >
                      <IconComponent
                        name="MessageSquare"
                        className="form-modal-chat-icon"
                      />
                    </div>
                  )}
                  {chat.thought && chat.thought !== "" && !hidden && (
                    <SanitizedHTMLWrapper
                      className="form-modal-chat-thought"
                      content={convert.toHtml(chat.thought ?? "")}
                      onClick={() => setHidden((prev) => !prev)}
                    />
                  )}
                  {chat.thought && chat.thought !== "" && !hidden && <br></br>}
                  <div className="flex w-full flex-col">
                    <div
                      className="flex w-full flex-col dark:text-white"
                      data-testid="div-chat-message"
                    >
                      <div
                        data-testid={
                          "chat-message-" + chat.sender_name + "-" + chatMessage
                        }
                        className="flex w-full flex-col"
                      >
                        {chatMessage === "" && isBuilding && lastMessage ? (
                          <IconComponent
                            name="MoreHorizontal"
                            className="h-8 w-8 animate-pulse"
                          />
                        ) : (
                          <div className="w-full">
                            {editMessage ? (
                              <EditMessageField
                                key={`edit-message-${chat.id}`}
                                message={decodedMessage}
                                onEdit={(message) => {
                                  handleEditMessage(message);
                                }}
                                onCancel={() => setEditMessage(false)}
                              />
                            ) : (
                              <MarkdownField
                                chat={chat}
                                isEmpty={isEmpty}
                                chatMessage={chatMessage}
                                editedFlag={editedFlag}
                              />
                            )}
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
            {!editMessage && (
              <div className="invisible absolute -bottom-8 left-0 group-hover:visible opacity-0 group-hover:opacity-100 transition-opacity duration-200 z-10">
                <div>
                  <EditMessageButton
                    onCopy={() => {
                      navigator.clipboard.writeText(chatMessage);
                    }}
                    onDelete={() => {}}
                    onEdit={() => setEditMessage(true)}
                    className="h-fit group-hover:visible"
                    isBotMessage={!chat.isSend}
                    onEvaluate={handleEvaluateAnswer}
                    evaluation={chat.properties?.positive_feedback}
                  />
                </div>
              </div>
            )}
          </div>
          <div id={lastMessage ? "last-chat-message" : undefined} />
        </div>
      )}
    </>
  );
};

// Export a memoized version to prevent unnecessary renders
export default memo(ChatMessage);