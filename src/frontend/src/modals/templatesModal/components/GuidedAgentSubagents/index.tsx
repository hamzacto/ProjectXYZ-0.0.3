import { useState, useCallback, useMemo, useEffect } from "react";
import { IconGitFork } from "@tabler/icons-react";
import BaseModal from "@/modals/baseModal";
import { SubagentsCategoryDisclosure } from "../SubagentsCategoryDisclosure";
import useFlowsManagerStore from "@/stores/flowsManagerStore";
import { nodeColors } from "@/utils/styleUtils";

interface GuidedAgentSubagentsProps {
    addedSubagents: any[];
    addSubagent: (subagent: any) => void;
    deleteSubagent: (subagent: any) => void;
}

export default function GuidedAgentSubagents({
    addedSubagents = [],
    addSubagent,
    deleteSubagent
}: GuidedAgentSubagentsProps) {
    const flows = useFlowsManagerStore((state) => state.flows);
    
    const [openCategories, setOpenCategories] = useState<string[]>([]);
    const [search, setSearch] = useState("");
    
    const availableFlows = useMemo(() => {
        // Filter out any flows that are already added as subagents
        // And ignore the current flow being created
        return (flows ?? []).filter(flow => 
            !addedSubagents.some(subagent => subagent.id === flow.id)
        );
    }, [flows, addedSubagents]);

    const handleAddSubagent = useCallback(
        (subagent: any) => {
            if (!addedSubagents.includes(subagent)) {
                addSubagent(subagent);
            }
        },
        [addedSubagents, addSubagent]
    );

    const handleDeleteSubagent = useCallback(
        (subagent: any) => {
            deleteSubagent(subagent);
        },
        [deleteSubagent]
    );

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

    useEffect(() => {
        const header = document.querySelector('.subagents-header');
        if (header) {
            header.classList.add('animate-in', 'fade-in', 'duration-300');
        }
    }, []);

    return (
        <div className="flex flex-1 flex-col gap-4">
            <BaseModal.Header 
                description="Connect other agent flows to enhance this agent's capabilities."
            >
                <span className="flex items-center gap-2">
                    <IconGitFork className="w-5 h-5" />
                    Connect Subagents
                </span>
            </BaseModal.Header>
            <SubagentsCategoryDisclosure
                item={{ display_name: "Subagents", name: "subagents", icon: "git-fork" }}
                openCategories={openCategories}
                setOpenCategories={setOpenCategories}
                flows={availableFlows}
                nodeColors={nodeColors}
                onDragStart={onDragStart}
                addSubagent={handleAddSubagent}
                addedSubagents={addedSubagents}
                deleteSubagent={handleDeleteSubagent}
            />
        </div>
    );
}
