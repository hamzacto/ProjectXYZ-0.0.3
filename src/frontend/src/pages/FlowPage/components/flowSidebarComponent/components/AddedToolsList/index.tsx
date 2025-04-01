import ShadTooltip from "@/components/common/shadTooltipComponent";
import { Badge } from "@/components/ui/badge";
import ForwardedIconComponent from "@/components/common/genericIconComponent";
import { cn } from "@/utils/utils";
import { useNavigate } from "react-router-dom";

interface AddedToolsListProps {
  tools: any[];
  deleteTool: (tool: any) => void;
  isServiceConnected?: (serviceName: string) => boolean;
}

export const AddedToolsList = ({ tools, deleteTool, isServiceConnected }: AddedToolsListProps) => {
  const navigate = useNavigate();

  // Helper function to determine if a service is connected
  const checkServiceConnection = (toolName: string) => {
    return isServiceConnected ? isServiceConnected(toolName) : true;
  };

  // Determine which service is needed based on the tool name
  const getServiceName = (name: string) => {
    const normalizedName = name.toLowerCase();
    if (normalizedName.includes('hubspot')) return 'HubSpot';
    if (normalizedName.includes('slack')) return 'Slack';
    if (normalizedName.includes('gmail') || normalizedName.includes('google')) return 'Gmail';
    return null;
  };

  // Get warning tooltip text
  const getWarningTooltip = (name: string) => {
    const serviceName = getServiceName(name);
    if (!serviceName) return null;
    return `This tool requires ${serviceName} integration. Click to connect your ${serviceName} account.`;
  };

  // Navigate to the relevant integration settings page
  const handleNavigateToIntegration = (toolName: string) => {
    const normalizedName = toolName.toLowerCase();
    if (normalizedName.includes('hubspot')) {
      navigate('/settings/integrations/hubspot');
    } else if (normalizedName.includes('slack')) {
      navigate('/settings/integrations/slack');
    } else if (normalizedName.includes('gmail') || normalizedName.includes('google')) {
      navigate('/settings/integrations/gmail');
    }
  };

  return (
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
          [...tools].reverse().map((tool, index) => {
            const isConnected = checkServiceConnection(tool.display_name);
            const serviceName = getServiceName(tool.display_name);
            const showWarning = !isConnected && serviceName;
            
            return (
              <div 
                key={index}
                className={cn(
                  "group relative rounded-md border border-border transition-colors",
                  showWarning 
                    ? "bg-yellow-50/10 border-yellow-500/40" 
                    : "bg-background hover:bg-accent/50"
                )}
              >
                <ShadTooltip styleClasses="z-50">
                  <div className="p-2.5">
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
                    
                    {showWarning && (
                      <div 
                        className="mt-2 flex items-center gap-2 p-2 text-xs bg-yellow-50/20 rounded-md border border-yellow-500/30 hover:bg-yellow-50/30"
                      >
                        <ForwardedIconComponent
                          name="AlertTriangle"
                          className="h-4 w-4 shrink-0 text-yellow-500"
                        />
                        <span>
                          Requires {serviceName} connection. <span className="text-primary font-medium"></span>
                        </span>
                      </div>
                    )}
                  </div>
                </ShadTooltip>
              </div>
            );
          })
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
};

export default AddedToolsList;