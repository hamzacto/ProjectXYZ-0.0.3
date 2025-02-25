import { convertTestName } from "@/components/common/storeCardComponent/utils/convert-test-name";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ForwardedIconComponent } from "@/components/common/genericIconComponent";
import ShadTooltip from "@/components/common/shadTooltipComponent";
import { Select, SelectContent, SelectItem, SelectTrigger } from "@/components/ui/select-custom";
import { DragEventHandler, forwardRef, useRef, useState } from "react";
import { cn } from "@/utils/utils";

export const SubagentSidebarDraggableComponent = forwardRef(
  (
    {
      sectionName,
      display_name,
      icon,
      itemName,
      error,
      color,
      onDragStart,
      subagent,
      official,
      beta,
      legacy,
      disabled,
      disabledTooltip,
      onAddSubagent,
      isAdded,
      addSubagent,
      description
    }: {
      sectionName: string;
      subagent: any;
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
      onAddSubagent?: (subagent: any) => void;
      isAdded: boolean;
      addSubagent: (subagent: any) => void;
    },
    ref,
  ) => {
    const [open, setOpen] = useState(false);
    const [cursorPos, setCursorPos] = useState({ x: 0, y: 0 });
    const popoverRef = useRef<HTMLDivElement>(null);

    const handlePointerDown = (e) => {
      if (!open) {
        const rect = popoverRef.current?.getBoundingClientRect() ?? {
          left: 0,
          top: 0,
        };
        setCursorPos({ x: e.clientX - rect.left, y: e.clientY - rect.top });
      }
    };

    const addSubagentHandler = (e) => {
      e.stopPropagation();
      e.preventDefault();
      
      const button = e.currentTarget;
      button.classList.add('add-button-pulse');
      
      setTimeout(() => {
        button.classList.remove('add-button-pulse');
      }, 400);
      
      addSubagent(subagent);
    };

    const handleKeyDown = (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        addSubagent(subagent);
      }
    };

    return (
      <Select
        onValueChange={() => {}}
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
                  </div>
                  <span className="truncate text-xs text-muted-foreground">
                    {description}
                  </span>
                </div>
                <div className="flex shrink-0 items-center gap-1">
                  {!isAdded ? (
                    <Button
                      data-testid={`add-subagent-button-${convertTestName(display_name)}`}
                      variant="ghost"
                      size="icon"
                      tabIndex={-1}
                      className="add-button text-primary transition-all duration-200"
                      onClick={addSubagentHandler}
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
                </div>
              </div>
            </div>
          </div>
        </ShadTooltip>
      </Select>
    );
  },
);

SubagentSidebarDraggableComponent.displayName = "SubagentSidebarDraggableComponent";

export default SubagentSidebarDraggableComponent; 