import { ForwardedIconComponent } from "@/components/common/genericIconComponent";
import { Button } from "@/components/ui/button";
import { cn } from "@/utils/utils";
import { Badge } from "@/components/ui/badge";
import { useMemo } from "react";

interface AddedSubagentsListProps {
  subagents: any[];
  deleteSubagent: (subagent: any) => void;
  addingSubagentId?: string;
}

export const AddedSubagentsList = ({ 
  subagents, 
  deleteSubagent,
  addingSubagentId
}: AddedSubagentsListProps) => {
  // Get the agent being added (if any)
  const addingSubagent = useMemo(() => {
    if (!addingSubagentId) return null;
    return subagents.find(s => s.id === addingSubagentId);
  }, [subagents, addingSubagentId]);

  return (
    <div className={cn(
      "h-full overflow-hidden rounded-lg border bg-background",
      "w-[300px]"
    )}>
      <div className="flex h-full flex-col">
        <div className="border-b px-4 py-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <ForwardedIconComponent 
                name="git-fork" 
                className="h-4 w-4 text-primary" 
              />
              <span className="text-sm font-medium">Added Subagents</span>
            </div>
            <Badge variant="secondary" className="h-5 px-2 text-xs">
              {subagents.length} connected
            </Badge>
          </div>
        </div>
        
        <div className="flex-1 overflow-visible p-2">
          {subagents.length === 0 && !addingSubagent ? (
            <div className="flex h-full flex-col items-center justify-center gap-2 p-4 text-center">
              <ForwardedIconComponent
                name="git-fork"
                className="h-8 w-8 text-muted-foreground/50"
              />
              <div className="space-y-1">
                <p className="text-sm font-medium">No subagents added</p>
                <p className="text-xs text-muted-foreground">
                  Add subagents from the available list to enhance your agent's capabilities.
                </p>
              </div>
            </div>
          ) : (
            <div className="space-y-2 p-1">
              {/* Show placeholder for agent being added */}
              {addingSubagent && (
                <div 
                  key={`placeholder-${addingSubagent.id}`}
                  className="flex items-center justify-between rounded-md border border-border bg-background p-2 hover:bg-muted/50 subagent-placeholder"
                >
                  <div className="flex items-center gap-2 overflow-hidden">
                    <ForwardedIconComponent
                      name="git-fork"
                      className="h-4 w-4 shrink-0 text-primary"
                    />
                    <div className="overflow-hidden">
                      <p className="truncate text-sm font-medium">{addingSubagent.name}</p>
                      <p className="truncate text-xs text-muted-foreground">
                        {addingSubagent.description || "An AI agent flow"}
                      </p>
                    </div>
                  </div>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => deleteSubagent(addingSubagent)}
                    className="h-7 w-7 text-muted-foreground hover:text-destructive"
                  >
                    <ForwardedIconComponent name="Trash2" className="h-4 w-4" />
                  </Button>
                </div>
              )}
              
              {/* Existing subagents */}
              {subagents.map((subagent) => (
                <div 
                  key={subagent.id}
                  className={cn(
                    "flex items-center justify-between rounded-md border border-border bg-background p-2 hover:bg-muted/50 subagent-item-enter",
                    addingSubagentId === subagent.id && "z-10"
                  )}
                  style={{
                    animationDelay: `${subagents.indexOf(subagent) * 0.05}s`
                  }}
                >
                  <div className="flex items-center gap-2 overflow-hidden">
                    <ForwardedIconComponent
                      name="git-fork"
                      className="h-4 w-4 shrink-0 text-primary"
                    />
                    <div className="overflow-hidden">
                      <p className="truncate text-sm font-medium">{subagent.name}</p>
                      <p className="truncate text-xs text-muted-foreground">
                        {subagent.description || "An AI agent flow"}
                      </p>
                    </div>
                  </div>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => deleteSubagent(subagent)}
                    className="h-7 w-7 text-muted-foreground hover:text-destructive"
                  >
                    <ForwardedIconComponent name="Trash2" className="h-4 w-4" />
                  </Button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}; 