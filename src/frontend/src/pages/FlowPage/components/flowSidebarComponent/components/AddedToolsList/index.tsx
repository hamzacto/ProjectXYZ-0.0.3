import ShadTooltip from "@/components/common/shadTooltipComponent";
import { Badge } from "@/components/ui/badge";
import ForwardedIconComponent from "@/components/common/genericIconComponent";
import { cn } from "@/utils/utils";

export const AddedToolsList = ({ tools, deleteTool }) => (
  <div className="flex flex-col min-w-[300px]">
    {/* Header Section */}
    <div className="sticky top-0 z-10 border-b bg-background px-4 py-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <ForwardedIconComponent name="Wrench" className="h-4 w-4 text-primary" />
          <span className="text-sm font-medium">Added Tools</span>
        </div>
        <Badge 
          variant="secondary" 
          className={cn(
            "h-5 rounded-md px-2",
            tools.length === 0 && "bg-muted text-muted-foreground"
          )}
        >
          {tools.length}
        </Badge>
      </div>
    </div>

    {/* Scrollable Content */}
    <div 
      className="flex flex-col gap-1.5 overflow-y-auto p-2" 
      style={{ height: '380px' }}
    >
      {tools.length > 0 ? (
        [...tools].reverse().map((tool, index) => (
          <ShadTooltip key={index} styleClasses="z-50">
            <div className="group relative rounded-md border border-border bg-background p-2.5 transition-colors hover:bg-accent/50">
              <div className="flex items-center gap-3">
                <div 
                  className="rounded-md border p-1.5"
                  style={{ borderColor: tool.color }}
                >
                  <ForwardedIconComponent 
                    name={tool.icon} 
                    className="h-4 w-4 shrink-0 text-primary" 
                  />
                </div>
                
                <div className="flex flex-1 items-center gap-2 overflow-hidden">
                  <span className="truncate text-sm font-medium">
                    {tool.display_name}
                  </span>
                  
                  {tool.beta && (
                    <Badge variant="pinkStatic" size="xq" className="shrink-0">
                      Beta
                    </Badge>
                  )}
                  {tool.legacy && (
                    <Badge variant="secondaryStatic" size="xq" className="shrink-0">
                      Legacy
                    </Badge>
                  )}
                </div>

                <ShadTooltip content="Remove tool">
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      deleteTool(tool);
                    }}
                    className="invisible rounded-md p-1 text-muted-foreground transition-colors hover:bg-secondary-hover hover:text-status-red group-hover:visible"
                    aria-label={`Remove ${tool.display_name}`}
                  >
                    <ForwardedIconComponent name="X" className="h-3.5 w-3.5" />
                  </button>
                </ShadTooltip>
              </div>
            </div>
          </ShadTooltip>
        ))
      ) : (
        <div className="flex h-full flex-col items-center justify-center gap-2 text-muted-foreground">
          <div className="rounded-md border border-dashed border-border p-3">
            <ForwardedIconComponent name="Wrench" className="h-6 w-6 opacity-50" />
          </div>
          <div className="text-center">
            <p className="text-sm font-medium">No tools added</p>
            <p className="text-xs">Add tools from the list on the left</p>
          </div>
        </div>
      )}
    </div>
  </div>
);

export default AddedToolsList;