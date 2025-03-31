import { memo, useCallback, useState, useEffect } from "react";
import { ForwardedIconComponent } from "@/components/common/genericIconComponent";
import { SidebarProvider } from "@/components/ui/sidebar";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/utils/utils";
import { AddedSubagentsList } from "./AddedSubagentsList";
import SubagentsSidebarItemsList from "./SubagentsSidebarItemsList";
import { api } from "../../../../controllers/API/api";
import { getURL } from "../../../../controllers/API/helpers/constants";
import "./index.css";

// Type definitions
interface CategoryItem {
  name: string;
  display_name: string;
  icon: string;
}

interface SubagentsCategoryDisclosureProps {
  item: CategoryItem;
  openCategories: string[];
  setOpenCategories: React.Dispatch<React.SetStateAction<string[]>>;
  flows: any[];
  nodeColors: Record<string, string>;
  onDragStart: (
    event: React.DragEvent<HTMLDivElement>,
    data: { type: string; node?: any }
  ) => void;
  addSubagent: (subagent: any) => void;
  addedSubagents: any[];
  deleteSubagent: (subagent: any) => void;
}

export const SubagentsCategoryDisclosure = memo(function SubagentsCategoryDisclosure({
  item,
  openCategories,
  setOpenCategories,
  flows,
  nodeColors,
  onDragStart,
  addSubagent,
  addedSubagents,
  deleteSubagent,
}: SubagentsCategoryDisclosureProps) {
  const [flowIcons, setFlowIcons] = useState<Record<string, string>>({});
  
  // Fetch icons for all flows and added subagents
  useEffect(() => {
    const fetchAllIcons = async () => {
      try {
        // Combine all flows to fetch icons for
        const allFlows = [...flows, ...addedSubagents.filter(
          subagent => !flows.some(flow => flow.id === subagent.id)
        )];
        
        const fetchPromises = allFlows.map(async (flow) => {
          if (flow.id) {
            try {
              const response = await api.get(`${getURL("FLOWS")}/${flow.id}`);
              if (response.data && response.data.icon) {
                return { id: flow.id, icon: response.data.icon };
              }
              return { id: flow.id, icon: "Sparkles" };
            } catch (error) {
              console.error(`Error fetching flow details for ${flow.id}:`, error);
              return { id: flow.id, icon: "Sparkles" };
            }
          }
          return null;
        });

        const results = await Promise.all(fetchPromises);
        const iconsMap = results.reduce((acc, result) => {
          if (result) {
            acc[result.id] = result.icon;
          }
          return acc;
        }, {});
        
        setFlowIcons(iconsMap);
      } catch (error) {
        console.error("Error fetching flow icons:", error);
      }
    };

    fetchAllIcons();
  }, [flows, addedSubagents]);
  
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

  const handleAddSubagent = useCallback(
    (subagent) => {
      if (!addedSubagents.includes(subagent)) {
        addSubagent(subagent);
      }
    },
    [addedSubagents, addSubagent]
  );

  return (
    <div className="tools-link-category-container">
      {/* Left Panel - Available Subagents */}
      <div className={cn(
        "flex-1 overflow-hidden rounded-lg border bg-background available-subagents-container",
        "min-w-0"
      )}>
        <div className="tools-link-category">
          <div className="border-b px-4 py-3 subagent-header">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <ForwardedIconComponent 
                  name={item.icon || "git-fork"} 
                  className="h-4 w-4 text-primary" 
                />
                <span className="text-sm font-medium">Available Subagents</span>
              </div>
              <Badge variant="secondary" className="h-5 px-2 text-xs">
                {flows.length} available
              </Badge>
            </div>
          </div>
          <div className="flex-1 overflow-y-auto p-2">
            <SubagentsSidebarItemsList
              flows={flows}
              nodeColors={nodeColors}
              onDragStart={onDragStart}
              onAddSubagent={handleAddSubagent}
              addedSubagents={addedSubagents}
              addSubagent={addSubagent}
              flowIcons={flowIcons}
            />
          </div>
        </div>
      </div>

      {/* Right Panel - Added Subagents */}
      <div className="w-[300px] added-subagents-container">
        <SidebarProvider>
          <AddedSubagentsList 
            subagents={addedSubagents} 
            deleteSubagent={deleteSubagent}
            flowIcons={flowIcons}
          />
        </SidebarProvider>
      </div>
    </div>
  );
});

SubagentsCategoryDisclosure.displayName = "SubagentsCategoryDisclosure"; 