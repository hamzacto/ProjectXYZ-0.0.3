import { convertTestName } from "@/components/common/storeCardComponent/utils/convert-test-name";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import useDeleteFlow from "@/hooks/flows/use-delete-flow";
import { useAddComponent } from "@/hooks/useAddComponent";
import { DragEventHandler, forwardRef, useRef, useState } from "react";
import IconComponent, {
    ForwardedIconComponent,
} from "../../../../../../components/common/genericIconComponent";
import ShadTooltip from "../../../../../../components/common/shadTooltipComponent";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
} from "../../../../../../components/ui/select-custom";
import { useDarkStore } from "../../../../../../stores/darkStore";
import useFlowsManagerStore from "../../../../../../stores/flowsManagerStore";
import { APIClassType } from "../../../../../../types/api";
import {
    createFlowComponent,
    downloadNode,
    getNodeId,
} from "../../../../../../utils/reactflowUtils";
import { cn, removeCountFromString } from "../../../../../../utils/utils";

export const ToolsLinkSidebarDraggableComponent = forwardRef(
    (
        {
            sectionName,
            display_name,
            icon,
            itemName,
            error,
            color,
            onDragStart,
            apiClass,
            official,
            beta,
            legacy,
            disabled,
            disabledTooltip,
            onAddTool, // Add this prop here
            isAdded,
            addTool,
            description,
            isConnected = true
        }: {
            sectionName: string;
            apiClass: APIClassType;
            icon: string;
            display_name: string;
            description: string;
            itemName: string;
            error: boolean;
            color: string;
            onDragStart: DragEventHandler<HTMLDivElement>;
            official: boolean;
            beta: boolean;
            legacy: boolean;
            disabled?: boolean;
            disabledTooltip?: string;
            onAddTool?: (apiClass: APIClassType) => void; // Define type for onAddTool
            isAdded: boolean;  // New prop
            addTool: any;
            isConnected?: boolean; // New prop to indicate if required service is connected
        },
        ref,
    ) => {
        //if (!["Gmail Email Loader", "Calculator", "Gmail Email Sender", "Google Search API", "Python Code Structured", "Python REPL", "Wikipedia API", "Wikidata API", "Yahoo Finance", "YouTube Transcripts"].includes(display_name)) return null;

        const [open, setOpen] = useState(false);
        const { deleteFlow } = useDeleteFlow();
        const flows = useFlowsManagerStore((state) => state.flows);
        const addComponent = useAddComponent();

        const version = useDarkStore((state) => state.version);
        const [cursorPos, setCursorPos] = useState({ x: 0, y: 0 });
        const popoverRef = useRef<HTMLDivElement>(null);

        // Determine which service is needed based on the tool name
        const getServiceName = () => {
            const normalizedName = display_name.toLowerCase();
            if (normalizedName.includes('hubspot')) return 'HubSpot';
            if (normalizedName.includes('slack')) return 'Slack';
            if (normalizedName.includes('gmail') || normalizedName.includes('google')) return 'Gmail';
            return null;
        };

        const serviceName = getServiceName();
        
        const getWarningTooltip = () => {
            if (isConnected || !serviceName) return null;
            return `This tool requires ${serviceName} integration. Please connect your ${serviceName} account in integrations settings.`;
        };

        const handlePointerDown = (e) => {
            if (!open) {
                const rect = popoverRef.current?.getBoundingClientRect() ?? {
                    left: 0,
                    top: 0,
                };
                setCursorPos({ x: e.clientX - rect.left, y: e.clientY - rect.top });
            }
        };

        const addComponentHandler = () => {
            addTool(apiClass);  // Add tool to the list
        };

        function handleSelectChange(value: string) {
            switch (value) {
                case "download":
                    const type = removeCountFromString(itemName);
                    downloadNode(
                        createFlowComponent(
                            { id: getNodeId(type), type, node: apiClass },
                            version,
                        ),
                    );
                    break;
                case "delete":
                    const flowId = flows?.find((f) => f.name === display_name);
                    if (flowId) deleteFlow({ id: flowId.id });
                    break;
            }
        }

        const handleKeyDown = (e) => {
            if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                addComponent(apiClass, itemName);
            }
        };

        return (
            <Select
                onValueChange={handleSelectChange}
                onOpenChange={(change) => setOpen(change)}
                open={open}
                key={itemName}
            >
                <ShadTooltip
                    content={disabled ? disabledTooltip : null}
                    styleClasses="z-50"
                >
                    <div
                        onPointerDown={handlePointerDown}
                        onContextMenuCapture={(e) => {
                            e.preventDefault();
                            setOpen(true);
                        }}
                        key={itemName}
                        data-tooltip-id={itemName}
                        tabIndex={0}
                        onKeyDown={handleKeyDown}
                        className="m-[1px] rounded-md outline-none ring-ring focus-visible:ring-1"
                    >
                        <div
                            data-testid={sectionName + display_name}
                            id={sectionName + display_name}
                            className={cn(
                                "tool-item group/draggable flex cursor-grab items-center gap-2 rounded-md p-3",
                                "transition-all duration-200 ease-in-out",
                                error && "cursor-not-allowed select-none",
                                disabled
                                    ? "pointer-events-none bg-accent text-placeholder-foreground"
                                    : "bg-muted text-foreground hover:bg-secondary-hover/75",
                                isAdded && "added"
                            )}
                            draggable={!error}
                            style={{
                                borderLeftColor: isAdded ? color : 'transparent'
                            }}
                            onDragStart={onDragStart}
                            onDragEnd={() => {
                                if (document.getElementsByClassName("cursor-grabbing").length > 0) {
                                    document.body.removeChild(
                                        document.getElementsByClassName("cursor-grabbing")[0],
                                    );
                                }
                            }}
                        >
                            <div className="flex w-full items-center gap-2">
                                <ForwardedIconComponent
                                    name={icon}
                                    className="h-5 w-5 shrink-0"
                                />
                                <div className="flex flex-1 flex-col overflow-hidden">
                                    <div className="flex items-center gap-2">
                                        <ShadTooltip styleClasses="z-50">
                                            <span className="truncate text-sm font-medium">
                                                {display_name}
                                            </span>
                                        </ShadTooltip>
                                        {beta && (
                                            <Badge
                                                variant="pinkStatic"
                                                size="xq"
                                                className="ml-1.5 shrink-0"
                                            >
                                                Beta
                                            </Badge>
                                        )}
                                        {legacy && (
                                            <Badge
                                                variant="secondaryStatic"
                                                size="xq"
                                                className="ml-1.5 shrink-0"
                                            >
                                                Legacy
                                            </Badge>
                                        )}
                                        {!isConnected && serviceName && (
                                            <ShadTooltip 
                                                content={getWarningTooltip()} 
                                                styleClasses="z-50"
                                            >
                                                <div className="flex items-center">
                                                    <ForwardedIconComponent
                                                        name="AlertTriangle"
                                                        className="h-4 w-4 shrink-0 text-yellow-500"
                                                    />
                                                </div>
                                            </ShadTooltip>
                                        )}
                                    </div>
                                    <span className="truncate text-xs text-muted-foreground">
                                        {description}
                                    </span>
                                </div>
                                <div className="flex shrink-0 items-center gap-1">
                                    
                                    {!isAdded ? (
                                        <Button
                                            data-testid={`add-component-button-${convertTestName(display_name)}`}
                                            variant="ghost"
                                            size="icon"
                                            tabIndex={-1}
                                            className="add-button text-primary transition-all duration-200"
                                            onClick={addComponentHandler}
                                        >
                                            <ForwardedIconComponent
                                                name="Plus"
                                                className="h-4 w-4 shrink-0 transition-all group-hover/draggable:opacity-100 group-focus/draggable:opacity-100 sm:opacity-0"
                                            />
                                        </Button>
                                    ) : (
                                        <ForwardedIconComponent
                                            name="CheckCircle2"
                                            className="h-4 w-4 shrink-0 text-primary animate-in fade-in duration-300"
                                        />
                                    )}
                                    {/* <div ref={popoverRef}>
                                        <ForwardedIconComponent
                                            name="GripVertical"
                                            className="h-4 w-4 shrink-0 text-muted-foreground group-hover/draggable:text-primary"
                                        />
                                        <SelectTrigger tabIndex={-1}></SelectTrigger>
                                    </div> */}
                                </div>
                            </div>
                        </div>
                    </div>
                </ShadTooltip>
            </Select>
        );
    },
);

export default ToolsLinkSidebarDraggableComponent;