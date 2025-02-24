import {
    Sidebar,
    SidebarContent,
    SidebarFooter,
    useSidebar,
} from "@/components/ui/sidebar";
import { useAddComponent } from "@/hooks/useAddComponent";
import { useShortcutsStore } from "@/stores/shortcuts";
import { useStoreStore } from "@/stores/storeStore";
import { checkChatInput } from "@/utils/reactflowUtils";
import {
    nodeColors,
    SIDEBAR_BUNDLES,
    SIDEBAR_CATEGORIES,
} from "@/utils/styleUtils";
import Fuse from "fuse.js";
import { cloneDeep } from "lodash";
import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useHotkeys } from "react-hotkeys-hook";
import useAlertStore from "../../../../stores/alertStore";
import useFlowStore from "../../../../stores/flowStore";
import { useTypesStore } from "../../../../stores/typesStore";
import { APIClassType } from "../../../../types/api";
import { CategoryGroup } from "@/pages/FlowPage/components/flowSidebarComponent/components/categoryGroup";
import sensitiveSort from "@/pages/FlowPage/components/extraSidebarComponent/utils/sensitive-sort";
import { SidebarHeaderComponent } from "@/pages/FlowPage/components/flowSidebarComponent/components/sidebarHeader";
import isWrappedWithClass from "@/pages/FlowPage/components/PageComponent/utils/is-wrapped-with-class";
import { applyLegacyFilter } from "@/pages/FlowPage/components/flowSidebarComponent/helpers/apply-legacy-filter";
import { applyBetaFilter } from "@/pages/FlowPage/components/flowSidebarComponent/helpers/apply-beta-filter";
import { applyEdgeFilter } from "@/pages/FlowPage/components/flowSidebarComponent/helpers/apply-edge-filter";
import { filteredDataFn } from "@/pages/FlowPage/components/flowSidebarComponent/helpers/filtered-data";
import { traditionalSearchMetadata } from "@/pages/FlowPage/components/flowSidebarComponent/helpers/traditional-search-metadata";
import { combinedResultsFn } from "@/pages/FlowPage/components/flowSidebarComponent/helpers/combined-results";
import { normalizeString } from "@/pages/FlowPage/components/flowSidebarComponent/helpers/normalize-string";
import { CategoryDisclosure } from "@/pages/FlowPage/components/flowSidebarComponent/components/categoryDisclouse";
import BaseModal from "@/modals/baseModal";
import "./style.css";
import { ToolsLinkCategoryDisclosure } from "../ToolsLinkCategoryDisclosure";

const CATEGORIES = SIDEBAR_CATEGORIES;
const BUNDLES = SIDEBAR_BUNDLES;

interface GuidedAgentsToolsLinkComponentProps {
    addTool: (tool: any) => void;
    addedTools: any[];
    deleteTool: (tool: any) => void;
}

export function GuidedAgentsToolsLinkComponent({
    addTool,
    addedTools,
    deleteTool,
}: GuidedAgentsToolsLinkComponentProps) {
    const { data, templates } = useTypesStore((state) => ({
        data: state.data,
        templates: state.templates,
    }));

    const handleAddTool = useCallback(
        (tool: any) => {
            if (!addedTools.includes(tool)) {
                addTool(tool);
            }
        },
        [addedTools, addTool]
    );

    const handleDeleteTool = useCallback(
        (tool: any) => {
            deleteTool(tool);
        },
        [deleteTool]
    );

    const { getFilterEdge, setFilterEdge, filterType, nodes } = useFlowStore((state) => ({
        getFilterEdge: state.getFilterEdge,
        setFilterEdge: state.setFilterEdge,
        filterType: state.filterType,
        nodes: state.nodes,
    }));

    const setErrorData = useAlertStore((state) => state.setErrorData);
    const setOpen = useSidebar().setOpen;
    const addComponent = useAddComponent();

    const [dataFilter, setDataFilter] = useState(data);
    const [search, setSearch] = useState("");
    const [fuse, setFuse] = useState<Fuse<any> | null>(null);
    const [openCategories, setOpenCategories] = useState<string[]>([]);
    const [showBeta, setShowBeta] = useState(true);
    const [showLegacy, setShowLegacy] = useState(false);

    const searchInputRef = useRef<HTMLInputElement | null>(null);
    const isInputFocused = searchInputRef.current === document.activeElement;

    const chatInputAdded = useMemo(() => checkChatInput(nodes), [nodes]);

    const handleClearSearch = useCallback(() => {
        setSearch("");
        setDataFilter(data);
        setOpenCategories([]);
    }, [data]);

    const handleInputChange = useCallback((event: React.ChangeEvent<HTMLInputElement>) => {
        setSearch(event.target.value);
    }, []);

    const searchResults = useMemo(() => {
        if (!search || !fuse) return null;
        const normalizedSearch = normalizeString(search);
        const fuseResults = fuse.search(search).map((result) => ({
            ...result,
            item: { ...result.item, score: result.score },
        }));

        return {
            fuseResults,
            combinedResults: combinedResultsFn(fuseResults, data),
            traditionalResults: traditionalSearchMetadata(data, normalizedSearch),
        };
    }, [search, fuse, data]);

    const filteredSearchData = useMemo(() => {
        if (!searchResults) return cloneDeep(data);
        return filteredDataFn(data, searchResults.combinedResults, searchResults.traditionalResults);
    }, [data, searchResults]);

    const finalFilteredData = useMemo(() => {
        let resultData = filteredSearchData;
        if (getFilterEdge?.length > 0) resultData = applyEdgeFilter(resultData, getFilterEdge);
        if (!showBeta) resultData = applyBetaFilter(resultData);
        if (!showLegacy) resultData = applyLegacyFilter(resultData);
        return resultData;
    }, [filteredSearchData, getFilterEdge, showBeta, showLegacy]);

    useEffect(() => {
        setFuse(
            new Fuse(
                Object.entries(data).flatMap(([category, items]) =>
                    Object.entries(items).map(([key, value]) => ({
                        ...value,
                        category,
                        key,
                    })),
                ),
                {
                    keys: ["display_name", "description", "type", "category"],
                    threshold: 0.2,
                    includeScore: true,
                },
            ),
        );
    }, [data]);

    const onDragStart = useCallback((event: React.DragEvent, data: { type: string; node?: any }) => {
        const clone = event.currentTarget.cloneNode(true) as HTMLElement;
        clone.style.position = "absolute";
        clone.style.width = "215px";
        clone.style.top = "-500px";
        clone.style.right = "-500px";
        clone.classList.add("cursor-grabbing");
        document.body.appendChild(clone);
        event.dataTransfer.setDragImage(clone, 0, 0);
        event.dataTransfer.setData("genericNode", JSON.stringify(data));
    }, []);

    return (
        <div className="flex flex-1 flex-col gap-4">
            <BaseModal.Header description="Give your agent the tools it needs to achieve its goal.">
                Connect New Tool
            </BaseModal.Header>
            <ToolsLinkCategoryDisclosure
                item={{ display_name: "Tools", name: "tools", icon: "Hammer" }}
                openCategories={openCategories}
                setOpenCategories={setOpenCategories}
                dataFilter={dataFilter}
                nodeColors={nodeColors}
                chatInputAdded={chatInputAdded}
                onDragStart={onDragStart}
                sensitiveSort={sensitiveSort}
                addTool={handleAddTool}
                addedTools={addedTools}
                deleteTool={handleDeleteTool}
            />
        </div>
    );
}

export default memo(GuidedAgentsToolsLinkComponent);