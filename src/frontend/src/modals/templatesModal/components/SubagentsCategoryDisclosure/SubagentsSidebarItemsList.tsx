import { FC } from "react";
import SubagentSidebarDraggableComponent from "./SubagentSidebarDraggableComponent";

interface SubagentsSidebarItemsListProps {
  flows: any[];
  nodeColors: Record<string, string>;
  onDragStart: (event: React.DragEvent<HTMLDivElement>, nodeData: any) => void;
  onAddSubagent: (subagent: any) => void;
  addedSubagents: any[];
  addSubagent: (subagent: any) => void;
}

const SubagentsSidebarItemsList: FC<SubagentsSidebarItemsListProps> = ({
  flows,
  nodeColors,
  onDragStart,
  onAddSubagent,
  addedSubagents,
  addSubagent,
}) => {
  return (
    <div className="flex flex-col gap-1 py-2">
      {flows.length === 0 ? (
        <div className="p-3 text-sm text-muted-foreground italic">
          No available flows found. Create more flows to use as subagents.
        </div>
      ) : (
        flows.map((flow) => {
          const isAdded = addedSubagents.some(subagent => subagent.id === flow.id);
          
          return (
            <SubagentSidebarDraggableComponent
              key={flow.id}
              sectionName="subagents"
              subagent={flow}
              icon="git-fork"
              onDragStart={(event) =>
                onDragStart(event, {
                  type: "subagent",
                  node: flow,
                })
              }
              display_name={flow.name}
              itemName={flow.id}
              color={nodeColors["agent"] || "purple"}
              error={false}
              official={false}
              beta={false}
              legacy={false}
              onAddSubagent={() => onAddSubagent(flow)}
              isAdded={isAdded}
              addSubagent={addSubagent}
              description={flow.description || "An AI agent flow."}
            />
          );
        })
      )}
    </div>
  );
};

export default SubagentsSidebarItemsList; 