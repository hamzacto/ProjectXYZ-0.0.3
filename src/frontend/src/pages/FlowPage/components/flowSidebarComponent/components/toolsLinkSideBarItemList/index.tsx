import ShadTooltip from "@/components/common/shadTooltipComponent";
import { removeCountFromString } from "@/utils/utils";
import ToolsLinkSidebarDraggableComponent from "../toolsLinkSideBarDraggableComponent";

interface ToolsLinkSidebarItemsListProps {
  item: { name: string; icon?: string };
  dataFilter: Record<string, Record<string, any>>;
  nodeColors: Record<string, string>;
  chatInputAdded: boolean;
  onDragStart: (event: React.DragEvent<HTMLDivElement>, nodeData: any) => void;
  sensitiveSort: (a: string, b: string) => number;
  onAddTool: (tool: any) => void;
  addedTools: any[]; // Adjust type based on the shape of your tool objects
  addTool: (tool: any) => void;
  isServiceConnected?: (serviceName: string) => boolean;
}

const ToolsLinkSidebarItemsList: React.FC<ToolsLinkSidebarItemsListProps> = ({
    item,
    dataFilter,
    nodeColors,
    onDragStart,
    sensitiveSort,
    onAddTool,
    addedTools,
    addTool,
    isServiceConnected,
}) => {
    const tools_to_hide = ['Astra DB CQL', 
        'Astra DB Tool',
        'Calculator [DEPRECATED]',
        'Google Search API', 
        'Google Serper API', 
        'Google Serper API [DEPRECATED]',
        'MCP Tools (SSE)','MCP Tools (stdio)', 
        'Python Code Structured', 
        'Python REPL',
        'Python REPL [DEPRECATED]', 
        'Search API', 
        'Search API [DEPRECATED]', 
        'SearXNG Search', 
        'Serp Search API', 
        'Serp Search API [DEPRECATED]', 
        'Tavily AI Search', 
        'Tavily AI Search [DEPRECATED]' 
        ,'Wikidata', 
        'Wikidata API [Deprecated]', 
        'Wikipedia API [Deprecated]',
        'WolframAlpha API',
        'Yahoo Finance',
        'Yahoo Finance [DEPRECATED]']

    // Helper function to check if a tool is already added
    const isToolAdded = (tool: any) => {
        return addedTools.some(addedTool => 
            addedTool.display_name === tool.display_name
        );
    };

    // Helper function to check if a tool should be hidden
    const shouldHideTool = (tool: any) => {
        return tools_to_hide.includes(tool.display_name);
    };

    // Check if service is connected, default to true if the prop is not provided
    const checkServiceConnection = (toolName: string) => {
        return isServiceConnected ? isServiceConnected(toolName) : true;
    };

    return (
        <div className="flex flex-col gap-1 py-2">
            {Object.keys(dataFilter[item.name])
                .sort((a, b) => {
                    const itemA = dataFilter[item.name][a];
                    const itemB = dataFilter[item.name][b];
                    return itemA.score && itemB.score
                        ? itemA.score - itemB.score
                        : sensitiveSort(itemA.display_name, itemB.display_name);
                })
                .filter(SBItemName => !shouldHideTool(dataFilter[item.name][SBItemName]))
                .map((SBItemName, idx) => {
                    const currentItem = dataFilter[item.name][SBItemName];
                    const isAdded = isToolAdded(currentItem);
                    
                    // Don't pass isConnected to the available tools list
                    return (
                        <ToolsLinkSidebarDraggableComponent
                            key={SBItemName}
                            sectionName={item.name}
                            apiClass={currentItem}
                            icon={currentItem.icon ?? item.icon ?? "Unknown"}
                            onDragStart={(event) =>
                                onDragStart(event, {
                                    type: removeCountFromString(SBItemName),
                                    node: currentItem,
                                })
                            }
                            display_name={currentItem.display_name}
                            itemName={SBItemName}
                            color={nodeColors[currentItem.type] || "blue"}
                            error={currentItem.error}
                            official={currentItem.official}
                            beta={currentItem.beta}
                            legacy={currentItem.legacy}
                            onAddTool={() => onAddTool(currentItem)}
                            isAdded={isAdded}
                            addTool={addTool}
                            description={currentItem.description}
                        />
                    );
                })}
        </div>
    );
};

export default ToolsLinkSidebarItemsList;