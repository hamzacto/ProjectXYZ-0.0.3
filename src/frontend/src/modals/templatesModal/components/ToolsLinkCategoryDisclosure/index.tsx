import { memo, useCallback } from "react";
import { ForwardedIconComponent } from "@/components/common/genericIconComponent";
import { SidebarProvider } from "@/components/ui/sidebar";
import ToolsLinkSidebarItemsList from "@/pages/FlowPage/components/flowSidebarComponent/components/toolsLinkSideBarItemList";
import { AddedToolsList } from "@/pages/FlowPage/components/flowSidebarComponent/components/AddedToolsList";
import { APIClassType } from "@/types/api";
import { cn } from "@/utils/utils";
import { Badge } from "@/components/ui/badge";
import "./index.css";

// Type definitions
interface CategoryItem {
  name: string;
  display_name: string;
  icon: string;
}

interface ToolsLinkCategoryDisclosureProps {
  item: CategoryItem;
  openCategories: string[];
  setOpenCategories: React.Dispatch<React.SetStateAction<string[]>>;
  dataFilter: Record<string, any>;
  nodeColors: Record<string, string>;
  chatInputAdded: boolean;
  onDragStart: (
    event: React.DragEvent<HTMLDivElement>,
    data: { type: string; node?: APIClassType }
  ) => void;
  sensitiveSort: (a: any, b: any) => number;
  addTool: (tool: any) => void;
  addedTools: any[];
  deleteTool: (tool: any) => void;
}

export const ToolsLinkCategoryDisclosure = memo(function ToolsLinkCategoryDisclosure({
  item,
  openCategories,
  setOpenCategories,
  dataFilter,
  nodeColors,
  chatInputAdded,
  onDragStart,
  sensitiveSort,
  addTool,
  addedTools,
  deleteTool,
}: ToolsLinkCategoryDisclosureProps) {
  const handleKeyDownInput = useCallback(
    (e: React.KeyboardEvent<HTMLDivElement>) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        setOpenCategories((prev) =>
          prev.includes(item.name)
            ? prev.filter((cat) => cat !== item.name)
            : [...prev, item.name]
        );
      }
    },
    [item.name, setOpenCategories]
  );

  const handleAddTool = useCallback(
    (tool) => {
      if (!addedTools.includes(tool)) {
        addTool(tool);
      }
    },
    [addedTools, addTool]
  );

  const getTotalToolsCount = () => {
    return Object.values(dataFilter[item.name] || {}).length;
  };

  return (
    <div className="tools-link-category-container">
      {/* Left Panel - Available Tools */}
      <div className={cn(
        "flex-1 overflow-hidden rounded-lg border bg-background",
        "min-w-0"
      )}>
        <div className="tools-link-category">
          <div className="border-b px-4 py-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <ForwardedIconComponent 
                  name={item.icon || "Hammer"} 
                  className="h-4 w-4 text-primary" 
                />
                <span className="text-sm font-medium">Available Tools</span>
              </div>
              <Badge variant="secondary" className="h-5 px-2 text-xs">
                {getTotalToolsCount()} available
              </Badge>
            </div>
          </div>
          <div className="flex-1 overflow-y-auto p-2">
            <ToolsLinkSidebarItemsList
              item={item}
              dataFilter={dataFilter}
              nodeColors={nodeColors}
              chatInputAdded={chatInputAdded}
              onDragStart={onDragStart}
              sensitiveSort={sensitiveSort}
              onAddTool={handleAddTool}
              addedTools={addedTools}
              addTool={addTool}
            />
          </div>
        </div>
      </div>

      {/* Right Panel - Added Tools */}
      <div className="w-[300px]">
        <SidebarProvider>
          <AddedToolsList tools={addedTools} deleteTool={deleteTool} />
        </SidebarProvider>
      </div>
    </div>
  );
});

ToolsLinkCategoryDisclosure.displayName = "ToolsLinkCategoryDisclosure";