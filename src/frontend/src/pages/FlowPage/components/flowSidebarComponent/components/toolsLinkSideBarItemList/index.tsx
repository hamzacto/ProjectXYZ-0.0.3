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
}) => {
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
                .map((SBItemName, idx) => {
                    const currentItem = dataFilter[item.name][SBItemName];
                    const isAdded = addedTools.includes(currentItem);

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