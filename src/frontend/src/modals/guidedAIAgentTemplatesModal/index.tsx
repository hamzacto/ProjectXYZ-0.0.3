import ForwardedIconComponent from "@/components/common/genericIconComponent";
import { Button } from "@/components/ui/button";
import { SidebarProvider } from "@/components/ui/sidebar";
import { useCustomNavigate } from "@/customization/hooks/use-custom-navigate";
import { track } from "@/customization/utils/analytics";
import useAddFlow from "@/hooks/flows/use-add-flow";
import { Category } from "@/types/templates/types";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { newFlowModalPropsType } from "../../types/components";
import BaseModal from "../baseModal";
import TemplateContentComponent from "../templatesModal/components/TemplateContentComponent";
import { Nav } from "../templatesModal/components/navComponent";
import GuidedAgentForm from "@/components/core/guidedagentform";
import useFlowsManagerStore from "@/stores/flowsManagerStore";
import useSaveFlow from "@/hooks/flows/use-save-flow";
import CreateAIAgentComponent from "../templatesModal/components/CreateGuidedAIAgentComponent";
import useAlertStore from "@/stores/alertStore";
import { AllNodeType, FlowType } from "@/types/flow";
import GuidedAiAgentCoreInstructions from "../templatesModal/components/GuidedAiAgentCoreInstructions";
import React, { useCallback, useRef } from 'react';
import {
    Background,
    ReactFlow,
    ReactFlowProvider,
    useReactFlow,
    useNodesState,
    useEdgesState,
    Edge,
    SelectionMode,
    Controls,
    MiniMap,
    Panel,
    Viewport
} from '@xyflow/react';
import { v4 as uuidv4 } from 'uuid';
import InstructionNode from "../templatesModal/components/guidedAgentFlowBuilder/CustomNode";
import ConditionNode from "../templatesModal/components/guidedAgentFlowBuilder/conditionNode";
import { addEdge } from "reactflow";
import StartPointNode from "../templatesModal/components/guidedAgentFlowBuilder/startPointNode";
import "./controlPanel.css";
import { GuidedAgentsToolsLinkComponent } from "../templatesModal/components/GuidedAgentToolsLinkComponent";
import { getNodeId } from "@/utils/reactflowUtils";
import { getNodeRenderType } from "@/utils/utils";
import KhownledgeBaseFilesUpload from "../templatesModal/components/GuidedAgentkhowledgeBase";
import { FileCategory, FileItem } from "../templatesModal/components/GuidedAgentkhowledgeBase/types";
import axios, { AxiosInstance, AxiosResponse } from "axios";
import GuidedAgentIntegrations from "../templatesModal/components/GuidedAgentIntegrations";
import GuidedAgentTriggers from "../templatesModal/components/GuidedAgentTriggers";
import { useIntegrationStore } from "@/stores/integrationStore";
import GuidedAgentAIAgentAdvancedSettings from "../templatesModal/components/GuidedAgentAIAgentAdvancedSettings";
import { GuidedAgentNavComponent } from "../templatesModal/components/GuidedAgentNavComponent";
import GuidedAgentModal from "../guidedAgentModal";
import GuidedAiAgentConfigureTemplate from "../templatesModal/components/GuidedAiAgentConfigureTemplate";
import GuidedAgentSubagents from "../templatesModal/components/GuidedAgentSubagents";


export default function GuidedAIAgentTemplatesModal({
    open,
    setOpen,
}: newFlowModalPropsType): JSX.Element {
    const [currentTab, setCurrentTab] = useState("guided-ai-agent");
    const addFlow = useAddFlow();
    const navigate = useCustomNavigate();
    const { folderId } = useParams();
    const [isGuidedAgentFormOpen, setIsGuidedAgentFormOpen] = useState(false);
    const [name, setName] = useState("");
    const [description, setDescription] = useState("");
    const [prompt, setPrompt] = useState("");
    const examples = useFlowsManagerStore((state) => state.examples);
    var flow = examples.find((example) => example.name === "Guided Agent");
    const setSuccessData = useAlertStore((state) => state.setSuccessData);
    const saveFlow = useSaveFlow();
    const [currentnodeid, setcurrentnodeid] = useState("");
    const [flowedges, setflowedges] = useEdgesState<Edge<any>>([]);
    const onConnect = (params) => setEdges((eds) => addEdge(params, eds));

    const [fileCategories, setFileCategories] = useState<FileCategory[]>([
        { id: 'default', name: 'General', files: [] }
    ]);
    const [activeCategory, setActiveCategory] = useState('default'); // Add activeCategory state

    const [selectedTriggers, setSelectedTriggers] = useState<string[]>([]);

    const [advancedSettings, setAdvancedSettings] = useState({
        temperature: 0.3,
        modelName: "gpt-3.5-turbo",
        maxRetries: 10,
        timeout: 700,
        seed: 1,
        jsonMode: false,
        maxTokens: 0,
        handleParseErrors: true
    });

    // const [templateVariables, setTemplateVariables] = useState<Array<{
    //     id: string;
    //     name: string;
    //     type: "Text" | "Long Text" | "Number" | "JSON";
    //     defaultValue: string;
    //     required: boolean;
    // }>>([
    //     {
    //         id: crypto.randomUUID(),
    //         name: "Company_name",
    //         type: "Text",
    //         defaultValue: "",
    //         required: true
    //     }
    // ]);

    const [addedSubagents, setAddedSubagents] = useState<any[]>([]);

    const handleAddSubagent = (subagent: any) => {
        if (!addedSubagents.some(s => s.id === subagent.id)) {
            setAddedSubagents((prev) => [...prev, subagent]);
        }
    };

    const handleDeleteSubagent = (subagent: any) => {
        setAddedSubagents((prev) => prev.filter((s) => s.id !== subagent.id));
    };

    const handleTriggersChange = (triggers: string[]) => {
        setSelectedTriggers(triggers);
    };

    const handleFilesUpdate = (updatedFiles: FileItem[]) => {
        // Update the files in the active category
        setFileCategories(prev => {
            const updatedCategories = prev.map(category =>
                category.id === activeCategory
                    ? { ...category, files: updatedFiles }
                    : category
            );
            return updatedCategories;
        });
    };


    const styles = {
        nodeContainer: 'nodeContainer',
        contentContainer: 'contentContainer',
        header: 'header',
        inputContainer: 'inputContainer',
        input: 'input',
        iconControl: 'iconControl',
        textarea: 'textarea',
        addButton: 'addButton',
        nodeWrapper: 'nodeWrapper',
        handleButtom: 'handleButtom',
        deleteButton: 'deleteButton',
        deleteIcon: 'deleteIcon',
        wrapperStyle: 'wrapperStyle',
        buttonStyle: 'buttonStyle',
    };

    // Flow state


    // FLOW BUILDER 

    const nodeTypes = {
        InstructionNode: InstructionNode,
        ConditionNode: ConditionNode,
        StartPointNode: StartPointNode,
    };

    const initialNodes = [
        {
            id: '1',
            type: 'StartPointNode',
            position: { x: 250, y: 0 },
            data: {
                label: 'Start Node',
                instruction: '', // Placeholder for user input
                onAddNode: (nodeType) => handleAddNode('1', nodeType), // Dynamically handle node addition
                onInputChange: (nodeId, newValue) => handleInputChange(nodeId, newValue), // Handle input changes
                onDeleteNode: () => handleDeleteNode('1'), // Dynamically handle node deletion
            },
        },
    ];

    const panOnDrag = [1, 2];
    const reactFlowWrapper = useRef<HTMLDivElement>(null);
    const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
    const [edges, setEdges, onEdgesChange] = useEdgesState<Edge<any>>([]);
    const [showMenu, setShowMenu] = useState(false);
    const [menuPosition, setMenuPosition] = useState({ x: 0, y: 0 });
    const [currentNodeId, setCurrentNodeId] = useState(null); // Track which node is clicked

    const { zoomIn, zoomOut, fitView } = useReactFlow(); // Correct use of hook within functional component

    const handleZoomIn = useCallback(() => zoomIn(), [zoomIn]);
    const handleZoomOut = useCallback(() => zoomOut(), [zoomOut]);
    const handleFitView = useCallback(() => fitView(), [fitView]);

    const [addedTools, setAddedTools] = useState<any[]>([]); // Adjust type as needed

    const handleAddTool = (tool: any) => {
        const newAddedTools = addedTools;
        console.log("newAddedTools", newAddedTools);
        if (!addedTools.includes(tool)) {
            setAddedTools((prev) => [...prev, tool]);
        }
    };

    // Callback to delete a tool:
    const handleDeleteTool = (tool: any) => {
        setAddedTools((prevTools) => prevTools.filter((t) => t !== tool));
    };

    // Helper function to find all descendants of a node
    const findDescendants = (nodeId, allEdges) => {
        const descendants: string[] = [];
        const stack = [nodeId];

        while (stack.length > 0) {
            const currentId = stack.pop();
            descendants.push(currentId);

            // Find edges where currentId is the source
            const childEdges = allEdges.filter((edge) => edge.source === currentId);
            childEdges.forEach((edge) => stack.push(edge.target));
        }

        return descendants;
    };

    const findDescendantsNodes = (nodeId, allEdges, allNodes) => {
        const descendants: typeof allNodes = [];
        const stack = [nodeId];

        while (stack.length > 0) {
            const currentId = stack.pop();

            // Add the node corresponding to the currentId to the descendants list
            const currentNode = allNodes.find((node) => node.id === currentId);
            if (currentNode && !descendants.some((node) => node.id === currentNode.id)) {
                descendants.push(currentNode);
            }

            // Find edges where currentId is the source
            const childEdges = allEdges.filter((edge) => edge.source === currentId);
            childEdges.forEach((edge) => stack.push(edge.target));
        }

        return descendants;
    };

    function findAncestors(
        nodeId: string,
        edges: { source: string; target: string }[],
        nodes: { id: string }[]
    ): { id: string }[] {
        const ancestors: { id: string }[] = [];

        function traverse(currentNodeId: string) {
            // Find the parent edges of the current node
            const parentEdges = edges.filter((edge) => edge.target === currentNodeId);

            // For each parent, find the node and traverse further
            parentEdges.forEach((edge) => {
                const parentNode = nodes.find((node) => node.id === edge.source);
                if (parentNode && !ancestors.some((ancestor) => ancestor.id === parentNode.id)) {
                    ancestors.push(parentNode);
                    traverse(parentNode.id); // Recursive call to find further ancestors
                }
            });
        }

        traverse(nodeId);

        return ancestors;
    }

    function findParentChildren(nodeId, edges, nodes) {
        // Step 1: Find the parent node
        const parentEdge = edges.find((edge) => edge.target === nodeId);
        if (!parentEdge) return []; // No parent exists

        const parentId = parentEdge.source;

        // Step 2: Find all children of the parent
        const parentChildrenIds = edges
            .filter((edge) => edge.source === parentId)
            .map((edge) => edge.target);

        // Step 3: Retrieve the child nodes
        const parentChildren = nodes.filter((node) =>
            parentChildrenIds.includes(node.id)
        );

        return parentChildren;
    }

    function hasGrandparentWithMultipleChildren(
        nodeId: string,
        edges: { source: string; target: string }[],
        nodes: { id: string }[]
    ): boolean {
        // Find all ancestors of the node
        const ancestors = findAncestors(nodeId, edges, nodes);

        // Iterate through ancestors to check if any have more than one child
        for (const ancestor of ancestors) {
            // Find all edges where the ancestor is the source
            const childrenEdges = edges.filter((edge) => edge.source === ancestor.id);

            // If the ancestor has more than one child, return true
            if (childrenEdges.length > 1) {
                return true;
            }
        }

        // No grandparent or higher ancestor has more than one child
        return false;
    }

    function updateDescendantsY(
        newNode: { id: string; type: string; position: { x: number; y: number }; data: { label: string; instruction: string; onAddNode: (nodeType: any) => void; onInputChange: (nodeId: any, newValue: any) => void; onDeleteNode: () => void; } },
        nodeId: string,
        edges: { source: string; target: string }[],
        nodes: { id: string; type: string; position: { x: number; y: number }; data: { label: string; instruction: string; onAddNode: (nodeType: any) => void; onInputChange: (nodeId: any, newValue: any) => void; onDeleteNode: () => void; } }[],
        offsetY: number = 300) {
        // Create a copy of the nodes to prevent direct mutation
        const updatedNodes = [...nodes];

        // Helper function to recursively find and update descendants
        function updateChildren(currentNodeId: string) {
            // Find all edges where the source is the current node (direct children)
            const childEdges = edges.filter((edge) => edge.source === currentNodeId);

            for (const edge of childEdges) {
                const childId = edge.target;

                // Find the child node in the nodes array and update its y position
                const childNode = updatedNodes.find((node) => node.id === childId);
                if (childNode) {
                    childNode.position.y += offsetY;
                }

                // Recursively update the children of this child node
                updateChildren(childId);
            }
        }

        // Start updating descendants from the given nodeId
        updateChildren(nodeId);

        // Update the nodes state in React Flow, keeping the existing properties (type, data)
        setNodes([...updatedNodes.map((node) => ({
            ...node, // Spread the existing properties of the node
        })), newNode]);
    }

    function hasAncestorWithMultipleChildren(nodeId, edges) {
        // Helper function to find the parent of a node
        const findParent = (childId) => {
            const parentEdge = edges.find(edge => edge.target === childId);
            return parentEdge ? parentEdge.source : null;
        };

        // Helper function to find children of a node
        const findChildren = (parentId) => {
            return edges.filter(edge => edge.source === parentId).map(edge => edge.target);
        };

        // Start from the current node and move up through its ancestors
        let currentNode = nodeId;

        while (currentNode) {
            // Find the parent of the current node
            const parent = findParent(currentNode);

            // If the parent exists, check if it has multiple children
            if (parent) {
                const children = findChildren(parent);
                if (children.length > 1) {
                    return true; // Found an ancestor with multiple children
                }
            }

            // Move to the parent node for the next iteration
            currentNode = parent;
        }

        // No ancestor with multiple children was found
        return false;
    }

    function getMiddleXOfChildren(nodeId, allEdges, allNodes, positionNodeId) {
        // Find the IDs of all children of the node
        const childIds = allEdges
            .filter((edge) => edge.source === nodeId)
            .map((edge) => edge.target);

        // Find the x-coordinates of the children nodes
        const childNodes = allNodes.filter((node) => childIds.includes(node.id));
        const childXCoordinates = childNodes.map((node) => node.position.x);
        const maxChildX = Math.max(...childXCoordinates);
        const minChildX = Math.min(...childXCoordinates);

        // Calculate the middle x-coordinate if there are children
        if (childXCoordinates.length > 0) {
            const sum = maxChildX + minChildX;
            return sum / 2;
        }

        // Return null if no children exist
        return positionNodeId;
    };

    function transformFlowToPrompt(nodes, edges) {
        const nodeMap = new Map();
        nodes.forEach(node => nodeMap.set(node.id, node));

        const edgeMap = new Map();
        edges.forEach(edge => {
            if (!edgeMap.has(edge.source)) {
                edgeMap.set(edge.source, []);
            }
            edgeMap.get(edge.source).push(edge.target);
        });

        let stepCounter = 0;  // Counter for step numbers

        function traverseNode(nodeId, depth = 0) {
            const node = nodeMap.get(nodeId);
            if (!node) return '';

            const indent = '  '.repeat(depth);
            let result = '';

            if (node.type === 'ConditionNode') {
                // Add Condition handling
                result += `${indent}Condition: ${node.data.instruction}\n`;
                const children = edgeMap.get(nodeId) || [];
                children.forEach(childId => {
                    result += traverseNode(childId, depth + 1);
                });
            } else {
                // For other nodes (Instruction Nodes)
                stepCounter++;  // Increment step number for non-condition nodes
                result += `${indent}Step ${stepCounter}: - ${node.data.instruction}\n`;

                const children = edgeMap.get(nodeId) || [];
                children.forEach(childId => {
                    result += traverseNode(childId, depth);
                });
            }

            return result;
        }

        // Assuming the starting node is the first InstructionNode in your flow
        const startNodeId = nodes.find(node => node.type === 'InstructionNode')?.id || '1';

        // The header explaining the flow
        const header = `Instructions: To better achieve your goal, follow this flow structure. 
    The flow is tree-like, with steps and conditions organized in a hierarchy. Each step represents a user action or response, and conditions dictate how the flow branches based on specific criteria (such as user input, system status, etc.).
    
    Follow these guidelines:

    1. Evaluate conditions: If a step contains a condition (e.g., "age > 18"), evaluate it based on the user's input. If the condition is true, proceed with the corresponding actions. If the condition is false, follow the alternative path.
    2. Branching: Only follow the child steps under a condition if the condition is met. Otherwise, proceed with the steps in the false branch.
    3. Handle user input: Ask for clarification if the user provides incomplete or ambiguous information. If necessary, ask follow-up questions to gather the information needed for the next step.
    4. Contextual adaptation: In real-life problems, conditions and steps may need to adapt based on the context. Always make sure to understand the full scope of the user's situation before proceeding.
    5. Hierarchy and Sequence: Ensure that each step is followed in the exact sequence, respecting the hierarchy of conditions and actions. Conditions may create new branches, but once a branch is selected, the steps under that branch must be followed until completion.
    
    Your task is to follow the instructions, evaluate conditions, and branch only when necessary. Make sure the user's responses are appropriately integrated into the flow and that the conversation adapts dynamically to different scenarios.
    
    Instructions:
    `;

        return header + '\n' + traverseNode(startNodeId).trim();
    }

    const handleAddNode = useCallback(
        (originNodeId, nodeType) => {
            //originNodeId = currentnodeid
            console.log("currentnodeid", currentnodeid)
            const originNode = nodes.find((node) => node.id === originNodeId);
            if (!originNode) return;

            const positionY = originNode.type === 'StartPointNode' ? originNode.position.y + 200 : originNode.position.y + 300;

            if (nodeType === "InstructionNode") {
                const id = uuidv4();
                const newNode = {
                    id,
                    type: nodeType,
                    position: { x: originNode.position.x, y: positionY },
                    data: {
                        label: `New Node ${id}`,
                        instruction: '', // Default empty instruction
                        onAddNode: (nodeType) => handleAddNode(id, nodeType), // Recursive node addition handler
                        onInputChange: (nodeId, newValue) => handleInputChange(nodeId, newValue), // Input change handler
                        onDeleteNode: () => handleDeleteNode(id),
                    },
                };

                // Find all condition nodes linked to the origin node
                const conditionNodes = nodes.filter((node) =>
                    edges.some((edge) => edge.source === originNodeId && edge.target === node.id && node.type === "ConditionNode")
                );

                if (conditionNodes.length > 0) {

                    const remainingEdges = edges.filter(
                        (edge) => edge.source !== originNodeId || !conditionNodes.some((node) => node.id === edge.target)
                    );

                    // Add edges from the new InstructionNode to all ConditionNodes
                    const newEdges = conditionNodes.map((conditionNode) => ({
                        id: `e${id}-${conditionNode.id}`,
                        source: id,
                        target: conditionNode.id,
                        type: 'default',
                    }));

                    // Find all descendant nodes of the new InstructionNode and the connected ConditionNodes
                    const affectedNodeIds = conditionNodes.flatMap((node) =>
                        findDescendants(node.id, edges)
                    );

                    // Update node positions for better layout, only for affected nodes
                    const updatedNodes = nodes.map((node) =>
                        affectedNodeIds.includes(node.id)
                            ? { ...node, position: { ...node.position, y: node.position.y + 300 } }
                            : node
                    );

                    // Add new node and updated nodes to the graph
                    setNodes([...updatedNodes, newNode]);

                    // Update edges: Link new InstructionNode to all existing ConditionNodes
                    setEdges((currentEdges) => [
                        ...remainingEdges,
                        ...newEdges,
                        { id: `e${originNodeId}-${id}`, source: originNodeId, target: id, type: 'default' },
                    ]);
                } else {
                    // If no condition nodes exist, add the InstructionNode normally
                    const offset = 300;
                    const originOriginNode = nodes.find((node) => node.id === originNodeId);
                    const existingChildNodes = nodes.filter((node) =>
                        edges.some((edge) => edge.source === originNodeId && edge.target === node.id)
                    );

                    const grandparentChildren = findParentChildren(originNodeId, edges, nodes);

                    const hasGrandparentWithMultipleChildrenCondition = hasGrandparentWithMultipleChildren(originNodeId, edges, nodes);

                    if (!hasGrandparentWithMultipleChildrenCondition) {
                        const updatedNodes = nodes.map((node) =>
                            node.position.y > originNode.position.y
                                ? { ...node, position: { ...node.position, y: node.position.y + offset } }
                                : node
                        );

                        setNodes([...updatedNodes, newNode]);
                    } else {

                        updateDescendantsY(newNode, originNodeId, edges, nodes, 300);
                    }

                    const childEdge = edges.find((edge) => edge.source === originNodeId);
                    const childId = childEdge?.target;
                    const childNode = nodes.find((node) => node.id === childId);

                    const newEdges = edges
                        .filter((edge) => edge.source !== originNodeId || edge.target !== childId)
                        .concat(
                            { id: `e${originNodeId}-${id}`, source: originNodeId, target: id, type: 'default' },
                            childId ? { id: `e${id}-${childId}`, source: id, target: childId, type: 'default' } : []
                        );

                    setEdges(newEdges);
                }
            } else if (nodeType === "ConditionNode") {

                const id = uuidv4();
                const childEdge = edges.find((edge) => edge.source === originNodeId);
                const childId = childEdge?.target;
                const childNode = nodes.find((node) => node.id === childId);
                const offset = 300;

                if (childNode === null || childNode === undefined || childNode.type === "InstructionNode") {

                    const newConditionNode = {
                        id,
                        type: nodeType,
                        position: { x: originNode.position.x, y: positionY },
                        data: {
                            label: `New Node ${id}`,
                            instruction: '', // Default empty instruction
                            onAddNode: (nodeType) => handleAddNode(id, nodeType), // Recursive node addition handler
                            onInputChange: (nodeId, newValue) => handleInputChange(nodeId, newValue), // Input change handler,
                            onDeleteNode: () => handleDeleteNode(id),
                        },
                    };

                    const hasGrandparentWithMultipleChildrenCondition = hasGrandparentWithMultipleChildren(originNodeId, edges, nodes);

                    if (!hasGrandparentWithMultipleChildrenCondition) {
                        const updatedNodes = nodes.map((node) =>
                            node.position.y > originNode.position.y
                                ? { ...node, position: { ...node.position, y: node.position.y + offset } }
                                : node
                        );

                        setNodes([...updatedNodes, newConditionNode]);
                    } else {

                        updateDescendantsY(newConditionNode, originNodeId, edges, nodes, 300);
                    }

                    // Update the edges
                    const newEdges = edges
                        .filter((edge) => edge.source !== originNodeId || edge.target !== childId)
                        .concat(
                            { id: `e${originNodeId}-${id}`, source: originNodeId, target: id, type: 'default' },
                            childId ? { id: `e${id}-${childId}`, source: id, target: childId, type: 'default' } : []
                        );

                    setEdges(newEdges);
                } else if (childNode.type === "ConditionNode") {
                    // Find all ancestor nodes of the origin node
                    const findAncestors = (nodeId, edges) => {
                        const parents = edges.filter((edge) => edge.target === nodeId).map((edge) => edge.source);
                        return parents.reduce(
                            (acc, parentId) => [...acc, parentId, ...findAncestors(parentId, edges)],
                            []
                        );
                    };

                    const ancestorIds = findAncestors(originNodeId, edges);
                    const descendants = findDescendantsNodes(originNodeId, edges, nodes);

                    // Find all child nodes of the origin node
                    const existingChildNodes = nodes.filter((node) =>
                        edges.some((edge) => edge.source === originNodeId && edge.target === node.id)
                    );

                    // Adjust positions of ancestor nodes
                    const updatedNodes = nodes.map((node) => {
                        if (((ancestorIds.includes(node.id) || originNodeId === node.id) || node.position.x > Math.max(...descendants.map((cnode) => cnode.position.x)) + 50) && !findDescendants(originNode, edges).includes(node.id)) {
                            const children = edges.filter((edge) => edge.source === node.id).map((edge) => edge.target);
                            if (hasAncestorWithMultipleChildren(node.id, edges) && node.id !== originNodeId) {
                                return {
                                    ...node,
                                    position: {
                                        ...node.position,
                                        x: node.position.x + 320, // Shift right
                                    },
                                };
                            } else {
                                return {
                                    ...node,
                                    position: {
                                        ...node.position,
                                        x: node.position.x + 150, // Shift right
                                    },
                                };
                            }
                        }
                        return node;
                    });

                    // Update nodes after processing ancestors
                    setNodes([...updatedNodes]);

                    // Calculate new node position
                    const horizontalSpacing = 320;
                    let newPositionX =
                        existingChildNodes.length > 0
                            ? Math.max(...existingChildNodes.map((node) => node.position.x)) + horizontalSpacing // Offset from last child
                            : originNode.position.x + horizontalSpacing; // If no children, offset from origin node

                    const descendantNodes = findDescendantsNodes(originNodeId, edges, nodes);

                    if (descendantNodes.length > 0) {
                        newPositionX = Math.max(...descendantNodes.map((node) => node.position.x)) + horizontalSpacing; // Offset from last descendant
                    }

                    const newPositionY = childNode.position.y;  // Align vertically with the origin node

                    // Create the new node
                    const newConditionNode = {
                        id,
                        type: nodeType,
                        position: { x: newPositionX, y: newPositionY },
                        data: {
                            label: `New Node ${id}`,
                            instruction: '', // Default empty instruction
                            onAddNode: (nodeType) => handleAddNode(id, nodeType), // Recursive node addition handler
                            onInputChange: (nodeId, newValue) => handleInputChange(nodeId, newValue), // Input change handler
                            onDeleteNode: () => handleDeleteNode(id),
                        },
                    };

                    // Add the new node
                    const allNodesWithNewNode = [...updatedNodes, newConditionNode];
                    setNodes(allNodesWithNewNode);

                    // Adjust positions of nodes with multiple children
                    const adjustedNodes = [...allNodesWithNewNode];

                    const findFirstChildNodeObject = (nodeId, edges, nodes) => {
                        const firstChildEdge = edges.find(edge => edge.source === nodeId);
                        if (firstChildEdge) {
                            return nodes.find(node => node.id === firstChildEdge.target) || null;
                        }
                        return null;
                    };

                    for (let i = 0; i < adjustedNodes.length; i++) {
                        const node = adjustedNodes[i];
                        const children = edges.filter((edge) => edge.source === node.id).map((edge) => edge.target);

                        if (children.length > 1) {
                            const newx = getMiddleXOfChildren(node.id, edges, adjustedNodes, node.position.x);
                            adjustedNodes[i] = {
                                ...node,
                                position: {
                                    ...node.position,
                                    x: Math.round(newx), // Update x to be in the middle
                                },
                            };
                        }

                        if (ancestorIds.includes(node.id) && children.length === 1) {
                            const firstChildNode = findFirstChildNodeObject(node.id, edges, adjustedNodes);
                            if (firstChildNode) {
                                adjustedNodes[i] = {
                                    ...node,
                                    position: {
                                        ...node.position,
                                        x: firstChildNode.position.x, // Align with first child
                                    },
                                };
                            }
                        }
                    }

                    // Add the new edge while retaining existing edges
                    const newEdge = { id: `e${originNodeId}-${id}`, source: originNodeId, target: id, type: 'default' };
                    setEdges((currentEdges) => [...currentEdges, newEdge]);

                    // Final update to nodes after adding edge
                    setNodes(adjustedNodes);


                }
            }
            console.log("Nodes", nodes);
            console.log("Edges", edges);

            const prompt = transformFlowToPrompt(nodes, edges);

            console.log("Prompt", prompt);
        },
        [nodes, edges, setNodes, setEdges, flowedges, setflowedges]
    );

    const handleDeleteNode = useCallback(
        (nodeId) => {
            // Find edges that involve the node being deleted
            const incomingEdge = edges.find((edge) => edge.target === nodeId); // Edge pointing to the node
            const outgoingEdges = edges.filter((edge) => edge.source === nodeId); // Edges pointing from the node

            // Find the node being deleted
            const nodeToDelete = nodes.find((node) => node.id === nodeId);

            setNodes((prevNodes) => {
                // Find all descendants of the node
                const descendantIds = findDescendants(nodeId, edges);

                // Check if the node is of type 'ConditionNode'
                if (nodeToDelete?.type === "ConditionNode") {
                    // Remove the node and all its descendants
                    return prevNodes.filter((node) => !descendantIds.includes(node.id) && node.id !== nodeId);
                }

                // Otherwise, just remove the node and adjust descendants' positions
                return prevNodes
                    .filter((node) => node.id !== nodeId) // Remove the specified node
                    .map((node) => {
                        if (descendantIds.includes(node.id)) {
                            // Shift up the position of descendant nodes
                            return {
                                ...node,
                                position: {
                                    ...node.position,
                                    y: node.position.y - 300, // Shift up
                                },
                            };
                        }
                        return node; // Keep unchanged nodes
                    });
            });

            if (nodeToDelete?.type === "InstructionNode") {

                setEdges((prevEdges) => {
                    // Find all edges related to the deleted node
                    const incomingEdge = prevEdges.find((edge) => edge.target === nodeId); // Edge coming into the deleted node
                    const outgoingEdges = prevEdges.filter((edge) => edge.source === nodeId); // Edges going out of the deleted node

                    // Remove all edges related to the deleted node
                    const filteredEdges = prevEdges.filter(
                        (edge) => edge.source !== nodeId && edge.target !== nodeId
                    );

                    // If the node has both an incoming edge and multiple outgoing edges
                    if (incomingEdge && outgoingEdges.length > 0) {
                        // Create new edges connecting the parent to each child
                        const newEdges = outgoingEdges.map((outgoingEdge) => ({
                            id: `e${incomingEdge.source}-${outgoingEdge.target}`,
                            source: incomingEdge.source,
                            target: outgoingEdge.target,
                            type: 'default',
                        }));

                        return [...filteredEdges, ...newEdges]; // Add the new edges
                    }

                    // If the node has a single incoming edge and no outgoing edges (end of chain)
                    if (incomingEdge && outgoingEdges.length === 0) {
                        return filteredEdges; // No new edges are needed
                    }

                    return filteredEdges; // Default case
                });
            } else if (nodeToDelete?.type === "ConditionNode") {

                setEdges((prevEdges) => {
                    // Find all edges related to the node
                    const descendantIds = findDescendants(nodeId, prevEdges);

                    // If the node is of type 'ConditionNode' and has multiple children, remove all edges related to the descendants
                    if (nodeToDelete?.type === "ConditionNode") {
                        return prevEdges.filter(
                            (edge) => !descendantIds.includes(edge.source) && !descendantIds.includes(edge.target)
                        );
                    }

                    // If the node has more than one child, remove all edges for the node and its descendants
                    if (outgoingEdges.length > 1) {
                        return prevEdges.filter(
                            (edge) => !descendantIds.includes(edge.source) && !descendantIds.includes(edge.target)
                        );
                    }

                    // Otherwise, remove only edges related to the deleted node
                    const filteredEdges = prevEdges.filter(
                        (edge) => edge.source !== nodeId && edge.target !== nodeId
                    );

                    // If the node has an incoming edge and outgoing edges, create new edges
                    if (incomingEdge && outgoingEdges.length > 0) {
                        // Connect the parent to each child
                        const newEdges = outgoingEdges.map((outgoingEdge) => ({
                            id: `e${incomingEdge.source}-${outgoingEdge.target}`,
                            source: incomingEdge.source,
                            target: outgoingEdge.target,
                            type: 'default',
                        }));

                        return [...filteredEdges, ...newEdges]; // Add the new edges
                    }

                    return filteredEdges; // Default case
                });
            }


        },
        [edges, setNodes, setEdges]
    );

    const handleInputChange = useCallback(
        (nodeId, newValue) => {
            setNodes((prevNodes) =>
                prevNodes.map((node) =>
                    node.id === nodeId
                        ? { ...node, data: { ...node.data, instruction: newValue } }
                        : node
                )
            );
        },
        [setNodes]
    );

    const axiosInstance = axios.create({
        baseURL: 'http://localhost:3000/api/v1', // Adjust to match your API base URL
        headers: {
            'Content-Type': 'application/json',
        },
        timeout: 120000,
    });

    function isValidBase64(base64String: string): boolean {
        const base64Regex = /^[A-Za-z0-9+/]+={0,2}$/;
        return base64String.length % 4 === 0 && base64Regex.test(base64String);
    }
    // A simple concurrency limiter
    async function processInBatches<T>(items: T[], handler: (item: T) => Promise<void>, concurrency: number = 4) {
        const executing: Promise<void>[] = [];
        const settled = new Map<Promise<void>, boolean>();

        for (const item of items) {
            const p = handler(item).then(() => {
                settled.set(p, true);
            });
            executing.push(p);
            if (executing.length >= concurrency) {
                await Promise.race(executing);
                // Remove resolved promises
                executing.splice(0, executing.length, ...executing.filter(p => !settled.get(p)));
            }
        }
        await Promise.all(executing);
    }

    async function insertFile(file: any, collectionName: string) {
        let base64Content: string | undefined;

        if (file.content instanceof ArrayBuffer) {
            base64Content = btoa(
                String.fromCharCode(...Array.from(new Uint8Array(file.content)))
            );
        } else if (
            typeof file.content === 'string' &&
            file.content.startsWith('data:application/pdf;base64,')
        ) {
            base64Content = file.content.split(',')[1];
        } else {
            console.error('Invalid file content format for', file.name);
            return;
        }

        if (!base64Content) {
            console.error('No content found for', file.name);
            return;
        }

        if (!isValidBase64(base64Content)) {
            console.error('Invalid Base64 content detected for', file.name);
            return;
        }

        const payload = {
            id: file.id,
            name: file.name,
            size: file.size,
            type: file.type,
            category: file.category,
            content: base64Content,
            file_path: file.file_path,
            collection_name: collectionName,
            batch_size: 50,
            chunk_size: 512,
            chunk_overlap: 200,
        };

        try {
            const { data } = await axiosInstance.post('/milvus/insert_file', payload);
            const taskId = data.task_id;
            console.log(`Task ${taskId} started for file ${file.name}`);

            // Poll for status updates
            const pollStatus = async () => {
                try {
                    const { data: status } = await axiosInstance.get(`/milvus/task/${taskId}`);
                    // Update UI progress if available
                    if (status.total_chunks > 0) {
                        const progress = (status.processed_chunks / status.total_chunks) * 100;
                        updateFileProgress(file.id, progress);
                    }
                    if (status.status === 'completed') {
                        console.log(`File ${file.name} processing completed`);
                        updateFileStatus(file.id, 'completed');
                        return;
                    } else if (status.status === 'failed') {
                        console.error(`File ${file.name} processing failed:`, status.error);
                        updateFileStatus(file.id, 'failed', status.error);
                        return;
                    }
                    // Poll again after a delay
                    setTimeout(pollStatus, 1000);
                } catch (error: any) {
                    console.error(`Error checking status for ${file.name}:`, error);
                    updateFileStatus(file.id, 'failed', error.message);
                }
            };
            pollStatus();
        } catch (error) {
            console.error(`Error inserting file ${file.name}:`, error);
        }
    }

    async function insertFilesIntoDatabase(fileCategories: any[], collectionName: string) {
        const files: any[] = [];
        fileCategories.forEach((cat) => {
            files.push(...cat.files);
        });
        // Process files with a concurrency limit of 4 (adjust as needed)
        await processInBatches(files, (file) => insertFile(file, collectionName), 4);
    }

    // Helper functions for UI updates
    function updateFileProgress(fileId: string, progress: number) {
        const progressElement = document.querySelector(`[data-file-id="${fileId}"] .progress`) as HTMLElement;
        if (progressElement) {
            progressElement.style.width = `${progress}%`;
        }
    }

    function updateFileStatus(fileId: string, status: 'completed' | 'failed', error?: string) {
        const statusElement = document.querySelector(`[data-file-id="${fileId}"] .status`);
        if (statusElement) {
            statusElement.textContent = status;
            if (error) {
                statusElement.setAttribute('title', error);
            }
        }
    }

    async function createCollectionInMilvus(collectionName: string) {
        try {
            const response = await axiosInstance.post(`/milvus/collections?collection_name=${collectionName}`);
            console.log(`Collection '${collectionName}' created successfully:`, response.data);
        } catch (error) {
            console.error('Error creating collection in Milvus:', error);
        }
    }

    // Add this at the top level of your component, with other hooks
    const flows = useFlowsManagerStore((state) => state.flows);

    const handleCreate = () => {
        const token = document.cookie
            .split('; ')
            .find(row => row.startsWith('access_token_lf='))
            ?.split('=')[1];

        if (!token) {
            throw new Error('No access token found');
        }

        console.log("AI Agent Created", { name, description, prompt });
        // console.log("Template Variables:", templateVariables);

        const collectionName = "agent_KB_" + Math.random().toString(36).substr(2, 9);
        let agentInstuctions = "";
        const BASIC_INSTRUCTIONS = "\n\nRULES:\n1. Never query the Vector Store with an empty string.\n2. If you don't know the answer, just say so. Don't make up an answer.\n3. If you are unsure about the answer, just say so. Don't make up an answer.";

        // Add template variables information to agent instructions
        let templateVarsText = "";
        // if (templateVariables.length > 0) {
        //     templateVarsText = "\n\nTEMPLATE VARIABLES:\n";
        //     templateVariables.forEach(variable => {
        //         templateVarsText += `- {{ ${variable.name} }}: ${variable.type}${variable.required ? ' (Required)' : ''}${variable.defaultValue ? ` - Default: ${variable.defaultValue}` : ''}\n`;
        //     });
        // }

        if (nodes.length > 1) {
            agentInstuctions = prompt + transformFlowToPrompt(nodes, edges) + templateVarsText + BASIC_INSTRUCTIONS;
        } else if (prompt) {
            agentInstuctions = prompt + templateVarsText + BASIC_INSTRUCTIONS;
        } else {
            agentInstuctions = "You are a helpful assistant that can answer questions and help with tasks." + templateVarsText + BASIC_INSTRUCTIONS;
        }
        // Find the new flow template (replace "new_flow_template_name" with the actual name or ID of the new template)
        // if(fileCategories[0].files.length === 0) {
        //     flow = examples.find((example) => example.name === "TemplateGuidedAgent");
        // }else{
        //     flow = examples.find((example) => example.name === "TemplateGuidedRAGAgent");
        // }
        flow = examples.find((example) => example.name === "TemplateGuidedAgentWithRag");
        if (!flow?.id || !flow?.data?.nodes) {
            console.error("Flow data is incomplete");
            return;
        }

        console.log("Tools Added", addedTools);
        const toolNodes = addedTools.map((tool, index) => {
            const toolId = getNodeId(tool.display_name); // Use the tool's display name as the type

            if (tool.display_name === "Gmail Fetcher Tool" || tool.display_name == "Gmail Sender Tool" || tool.display_name == "Gmail Responder Tool" || tool.display_name == "Gmail Draft Tool") {
                tool.template.api_key.value = "m1m8sy261xzb4l4hjmwq";
                tool.template.api_key.load_from_db = false;
            }


            if (tool.display_name === "Gmail Email Loader" 
                || tool.display_name === "Gmail Email Sender" 
                || tool.display_name === "Gmail Email Responder" 
                || tool.display_name === "Gmail Email Draft Creator"
                || tool.display_name === "Google Calendar Event Creator"
                || tool.display_name === "Google Calendar Event Loader"
                || tool.display_name === "Google Calendar Event Modifier"
                || tool.display_name === "Google Sheets Data Loader"
                || tool.display_name === "Google Sheets Data Modifier") {
                // Get the access token from cookies
                const token = document.cookie
                    .split('; ')
                    .find(row => row.startsWith('access_token_lf='))
                    ?.split('=')[1];

                if (!token) {
                    throw new Error('No access token found');
                }

                // Decode the JWT to get the user ID
                const base64Url = token.split('.')[1];
                const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
                const jsonPayload = decodeURIComponent(atob(base64).split('').map(function (c) {
                    return '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2);
                }).join(''));

                const { sub: user_id } = JSON.parse(jsonPayload);
                console.log("User ID", user_id);

                // Set the user_id in the tool template
                tool.template.user_id.value = user_id;
            }


            return {
                id: toolId,
                type: getNodeRenderType("genericnode"),
                position: { x: 200 * (index + 1), y: 100 }, // Adjust position as needed
                data: {
                    node: tool,
                    showNode: !tool.minimized,
                    type: tool.display_name, // Use the tool's display name as the type
                    id: toolId,
                },
            };
        });

        const agentNode = flow?.data?.nodes?.find(node => node.data?.type === "ToolCallingAgent");

        const userFlowNames = flows?.map((flow) => flow.name) || [];
        // Create nodes for the subagents
        const subagentNodes = addedSubagents.map((subagent, index) => {
            // Generate a unique ID for the subagent node
            const subagentNodeId = `RunFlow-${Math.random().toString(36).substring(2, 7)}`;
            
            // Calculate position
            const posX = 1043.0266059303253;
            const posY = -270.7925864199767 + (index * 100);
            
            
            return {
                "id": subagentNodeId,
                "type": "genericNode",
                "position": {
                  "x": posX,
                  "y": posY
                },
                "data": {
                  "node": {
                    "template": {
                      "_type": "Component",
                      "code": {
                        "type": "code",
                        "required": true,
                        "placeholder": "",
                        "list": false,
                        "show": true,
                        "multiline": true,
                        "value": "from typing import Any\n\nfrom loguru import logger\n\nfrom langflow.base.tools.run_flow import RunFlowBaseComponent\nfrom langflow.helpers.flow import run_flow\nfrom langflow.schema import dotdict\n\n\nclass RunFlowComponent(RunFlowBaseComponent):\n    display_name = \"Run Flow\"\n    description = (\n        \"Creates a tool component from a Flow that takes all its inputs and runs it. \"\n        \" \\n **Select a Flow to use the tool mode**\"\n    )\n    beta = True\n    name = \"RunFlow\"\n    icon = \"Workflow\"\n\n    inputs = RunFlowBaseComponent._base_inputs\n    outputs = RunFlowBaseComponent._base_outputs\n\n    async def update_build_config(self, build_config: dotdict, field_value: Any, field_name: str | None = None):\n        if field_name == \"flow_name_selected\":\n            build_config[\"flow_name_selected\"][\"options\"] = await self.get_flow_names()\n            missing_keys = [key for key in self.default_keys if key not in build_config]\n            if missing_keys:\n                msg = f\"Missing required keys in build_config: {missing_keys}\"\n                raise ValueError(msg)\n            if field_value is not None:\n                try:\n                    graph = await self.get_graph(field_value)\n                    build_config = self.update_build_config_from_graph(build_config, graph)\n                except Exception as e:\n                    msg = f\"Error building graph for flow {field_value}\"\n                    logger.exception(msg)\n                    raise RuntimeError(msg) from e\n        return build_config\n\n    async def run_flow_with_tweaks(self):\n        tweaks: dict = {}\n\n        flow_name_selected = self._attributes.get(\"flow_name_selected\")\n        parsed_flow_tweak_data = self._attributes.get(\"flow_tweak_data\", {})\n        if not isinstance(parsed_flow_tweak_data, dict):\n            parsed_flow_tweak_data = parsed_flow_tweak_data.dict()\n\n        if parsed_flow_tweak_data != {}:\n            for field in parsed_flow_tweak_data:\n                if \"~\" in field:\n                    [node, name] = field.split(\"~\")\n                    if node not in tweaks:\n                        tweaks[node] = {}\n                    tweaks[node][name] = parsed_flow_tweak_data[field]\n        else:\n            for field in self._attributes:\n                if field not in self.default_keys and \"~\" in field:\n                    [node, name] = field.split(\"~\")\n                    if node not in tweaks:\n                        tweaks[node] = {}\n                    tweaks[node][name] = self._attributes[field]\n\n        return await run_flow(\n            inputs=None,\n            output_type=\"all\",\n            flow_id=None,\n            flow_name=flow_name_selected,\n            tweaks=tweaks,\n            user_id=str(self.user_id),\n            session_id=self.graph.session_id or self.session_id,\n        )\n",
                        "fileTypes": [],
                        "file_path": "",
                        "password": false,
                        "name": "code",
                        "advanced": true,
                        "dynamic": true,
                        "info": "",
                        "load_from_db": false,
                        "title_case": false
                      },
                      "flow_name_selected": {
                        "tool_mode": false,
                        "trace_as_metadata": true,
                        "options": userFlowNames, // Use dynamic flow names here
                        "options_metadata": [],
                        "combobox": false,
                        "dialog_inputs": {},
                        "required": false,
                        "placeholder": "",
                        "show": true,
                        "name": "flow_name_selected",
                        "display_name": "Flow Name",
                        "advanced": false,
                        "dynamic": false,
                        "info": "The name of the flow to run.",
                        "real_time_refresh": true,
                        "refresh_button": true,
                        "title_case": false,
                        "type": "str",
                        "_input_type": "DropdownInput",
                        "value": subagent.name
                      },
                      // Other template properties remain the same
                      "tools_metadata": {
                        "tool_mode": false,
                        "is_list": true,
                        "list_add_label": "Add More",
                        "table_schema": {
                          "columns": [
                            {
                              "name": "name",
                              "display_name": "Tool Name",
                              "sortable": false,
                              "filterable": false,
                              "type": "text",
                              "description": "Specify the name of the tool.",
                              "disable_edit": false,
                              "edit_mode": "inline",
                              "hidden": false,
                              "formatter": "text"
                            },
                            {
                              "name": "description",
                              "display_name": "Tool Description",
                              "sortable": false,
                              "filterable": false,
                              "type": "text",
                              "description": "Describe the purpose of the tool.",
                              "disable_edit": false,
                              "edit_mode": "popover",
                              "hidden": false,
                              "formatter": "text"
                            },
                            {
                              "name": "tags",
                              "display_name": "Tool Identifiers",
                              "sortable": false,
                              "filterable": false,
                              "type": "text",
                              "description": "The default identifiers for the tools and cannot be changed.",
                              "disable_edit": true,
                              "edit_mode": "inline",
                              "hidden": true,
                              "formatter": "text"
                            }
                          ]
                        },
                        "trigger_text": "",
                        "trigger_icon": "Hammer",
                        "table_icon": "Hammer",
                        "table_options": {
                          "block_add": true,
                          "block_delete": true,
                          "block_edit": true,
                          "block_sort": true,
                          "block_filter": true,
                          "block_hide": true,
                          "block_select": true,
                          "hide_options": true,
                          "field_parsers": {
                            "name": [
                              "snake_case",
                              "no_blank"
                            ],
                            "commands": "commands"
                          },
                          "description": "Modify tool names and descriptions to help agents understand when to use each tool."
                        },
                        "trace_as_metadata": true,
                        "required": false,
                        "placeholder": "",
                        "show": true,
                        "name": "tools_metadata",
                        "value": [
                          {
                            "name": `${subagent.name}_tool_RunFlow-data_output`,
                            "description": `Tool designed to execute the flow '${subagent.name}'. Flow details: ${subagent.description || ""}. Output details: data_output() - Creates a tool component from a Flow that takes all its inputs and runs it.  \n **Select a Flow to use the tool mode**`,
                            "tags": [
                              `${subagent.name}_tool_RunFlow-data_output`
                            ]
                          },
                          {
                            "name": `${subagent.name}_tool_RunFlow-dataframe_output`,
                            "description": `Tool designed to execute the flow '${subagent.name}'. Flow details: ${subagent.description || ""}. Output details: dataframe_output() - Creates a tool component from a Flow that takes all its inputs and runs it.  \n **Select a Flow to use the tool mode**`,
                            "tags": [
                              `${subagent.name}_tool_RunFlow-dataframe_output`
                            ]
                          },
                          {
                            "name": `${subagent.name}_tool_RunFlow-message_output`,
                            "description": `Tool designed to execute the flow '${subagent.name}'. Flow details: ${subagent.description || ""}. Output details: message_output() - Creates a tool component from a Flow that takes all its inputs and runs it.  \n **Select a Flow to use the tool mode**`,
                            "tags": [
                              `${subagent.name}_tool_RunFlow-message_output`
                            ]
                          }
                        ],
                        "display_name": "Edit tools",
                        "advanced": false,
                        "dynamic": false,
                        "info": "",
                        "real_time_refresh": true,
                        "title_case": false,
                        "type": "table",
                        "_input_type": "TableInput"
                      }
                    },
                    "description": "Creates a tool component from a Flow that takes all its inputs and runs it.  \n **Select a Flow to use the tool mode**",
                    "icon": "Workflow",
                    "base_classes": [
                      "Data",
                      "DataFrame",
                      "Message"
                    ],
                    "display_name": "Run Flow",
                    "documentation": "",
                    "minimized": false,
                    "custom_fields": {},
                    "output_types": [],
                    "pinned": false,
                    "conditional_paths": [],
                    "frozen": false,
                    "outputs": [
                      {
                        "types": [
                          "Tool"
                        ],
                        "selected": "Tool",
                        "name": "component_as_tool",
                        "hidden": null,
                        "display_name": "Toolset",
                        "method": "to_toolkit",
                        "value": "__UNDEFINED__",
                        "cache": true,
                        "required_inputs": null,
                        "allows_loop": false,
                        "tool_mode": true
                      }
                    ],
                    "field_order": [
                      "flow_name_selected",
                      "session_id"
                    ],
                    "beta": true,
                    "legacy": false,
                    "edited": false,
                    "metadata": {},
                    "tool_mode": true,
                    "category": "logic",
                    "key": "RunFlow",
                    "score": 8.569061098350962e-12,
                    "lf_version": "1.1.5"
                  },
                  "showNode": true,
                  "type": "RunFlow",
                  "id": subagentNodeId
                },
                "selected": false,
                "measured": {
                  "width": 320,
                  "height": 436
                },
                "dragging": false
              };
        });

        // Create edges for the subagent nodes
        const subagentEdges = subagentNodes.map(subagentNode => {
            const agentNodeId = flow?.data?.nodes?.[7]?.id || '';
            
            // Create source and target handles
            const sourceHandle = `{œdataTypeœ:œRunFlowœ,œidœ:œ${subagentNode.id}œ,œnameœ:œcomponent_as_toolœ,œoutput_typesœ:[œToolœ]}`;
            const targetHandle = `{œfieldNameœ:œtoolsœ,œidœ:œ${agentNodeId}œ,œinputTypesœ:[œToolœ],œtypeœ:œotherœ}`;
            
            // Return the edge object
            return {
                "source": subagentNode.id,
                "sourceHandle": sourceHandle,
                "target": agentNodeId,
                "targetHandle": targetHandle,
                "data": {
                  "targetHandle": {
                    "fieldName": "tools",
                    "id": agentNodeId,
                    "inputTypes": ["Tool"],
                    "type": "other"
                  },
                  "sourceHandle": {
                    "dataType": "RunFlow",
                    "id": subagentNode.id,
                    "name": "component_as_tool",
                    "output_types": ["Tool"]
                  }
                },
                "id": `xy-edge__${subagentNode.id}${sourceHandle}-${agentNodeId}${targetHandle}`,
                "animated": false,
                "className": ""
            };
        });

        // Now update the flow data to include subagent nodes and edges
        const updatedFlow = {
            id: "",
            name: name,
            description: description,
            data: {
                // Include nodes for the base flow plus tools and subagents
                nodes: [
                    ...flow.data.nodes.map((node): AllNodeType => {
                        if (node.data.id.includes("Prompt")) {
                            return {
                                ...node,
                                data: {
                                    ...node.data,
                                    node: {
                                        ...node.data.node,
                                        template: {
                                            ...node.data.node.template,
                                            template: {
                                                ...node.data.node.template.template,
                                                value: agentInstuctions,
                                            },
                                        },
                                    },
                                },
                            } as AllNodeType;
                        }
                        if (node.data.type === "OpenAIModel") {
                            return {
                                ...node,
                                data: {
                                    ...node.data,
                                    node: {
                                        ...node.data.node,
                                        template: {
                                            ...node.data.node.template,
                                            model_name: {
                                                ...node.data.node.template.model_name,
                                                value: advancedSettings.modelName,
                                            },
                                            temperature: {
                                                ...node.data.node.template.temperature,
                                                value: advancedSettings.temperature,
                                            },
                                            json_mode: {
                                                ...node.data.node.template.json_mode,
                                                value: advancedSettings.jsonMode,
                                            },
                                            max_tokens: {
                                                ...node.data.node.template.max_tokens,
                                                value: advancedSettings.maxTokens,
                                            },
                                            timeout: {
                                                ...node.data.node.template.timeout,
                                                value: advancedSettings.timeout,
                                            },
                                            seed: {
                                                ...node.data.node.template.seed,
                                                value: advancedSettings.seed,
                                            }
                                        }
                                    }
                                }
                            } as AllNodeType;
                        }

                        if (node.data.id.includes("Milvus")) {
                            return {
                                ...node,
                                data: {
                                    ...node.data,
                                    node: {
                                        ...node.data.node,
                                        template: {
                                            ...node.data.node.template,
                                            collection_name: {
                                                ...node.data.node.template.collection_name,
                                                value: collectionName,
                                            }
                                        },
                                    },
                                },
                            } as AllNodeType;
                        }

                        if (node.data.id.includes("OpenAIEmbeddings")) {
                            return {
                                ...node,
                                data: {
                                    ...node.data,
                                    node: {
                                        ...node.data.node,
                                        template: {
                                            ...node.data.node.template,
                                            model: {
                                                ...node.data.node.template.model,
                                                value: "text-embedding-3-small",
                                            },
                                        }
                                    }
                                }
                            } as AllNodeType;
                        }

                        if (node.data.id.includes("OpenAIToolsAgent")) {
                            return {
                                ...node,
                                data: {
                                    ...node.data,
                                    node: {
                                        ...node.data.node,
                                        template: {
                                            ...node.data.node.template,
                                            max_iterations: {
                                                ...node.data.node.template.max_iterations,
                                                value: advancedSettings.maxRetries,
                                            },
                                            handle_parsing_errors: {
                                                ...node.data.node.template.handle_parsing_errors,
                                                value: advancedSettings.handleParseErrors,
                                            }
                                        }
                                    }
                                }
                            } as AllNodeType;
                        }

                        const modifyNode = (field, value) => {
                            updatedNode.data.node.template[field] = {
                                ...updatedNode.data.node.template[field],
                                value: value
                            };
                        };

                        const updatedNode = { ...node };
                        const componentType = updatedNode.data.type;
                        if (componentType === "Gmail Fetcher Tool") {
                            modifyNode('api_key', "m1m8sy261xzb4l4hjmwq"); // Composio API key
                        }

                        return node as AllNodeType;
                    }),
                    ...toolNodes, // Add the tool nodes to the flow
                    ...subagentNodes, // Add the subagent nodes to the flow
                ],
                edges: [
                    ...flow.data.edges,
                    // Add edges to connect the tools to the AI agent node
                    ...toolNodes.map((toolNode) => {
                        const sourceHandle = `{œdataTypeœ:œ${toolNode.data.type}œ,œidœ:œ${toolNode.id}œ,œnameœ:œapi_build_toolœ,œoutput_typesœ:[œToolœ]}`;
                        const targetHandle = `{œfieldNameœ:œtoolsœ,œidœ:œ${flow?.data?.nodes?.[7]?.id || ''}œ,œinputTypesœ:[œToolœ],œtypeœ:œotherœ}`;

                        console.log({
                            id: `xy-edge__${toolNode.id}${sourceHandle}-${flow?.data?.nodes?.[7]?.id || ''}${targetHandle}`,
                            source: toolNode.id,
                            target: flow?.data?.nodes?.[7]?.id || '',
                            sourceHandle: sourceHandle,
                            targetHandle: targetHandle,
                            data: {
                                targetHandle: {
                                    fieldName: "tools",
                                    id: flow?.data?.nodes?.[7]?.id || '',
                                    inputTypes: ["Tool"],
                                    type: "other",
                                },
                                sourceHandle: {
                                    dataType: toolNode.data.type,
                                    id: toolNode.id,
                                    name: "api_build_tool",
                                    output_types: ["Tool"],
                                },
                            },
                            className: "",
                            selected: false,
                        });

                        return {
                            id: `xy-edge__${toolNode.id}${sourceHandle}-${flow?.data?.nodes?.[7]?.id || ''}${targetHandle}`,
                            source: toolNode.id,
                            target: flow?.data?.nodes?.[7]?.id || '', // Use the found agent node instead of assuming position
                            sourceHandle: sourceHandle,
                            targetHandle: targetHandle,
                            data: {
                                targetHandle: {
                                    fieldName: "tools",
                                    id: flow?.data?.nodes?.[7]?.id || '',
                                    inputTypes: ["Tool"],
                                    type: "other",
                                },
                                sourceHandle: {
                                    dataType: toolNode.data.type,
                                    id: toolNode.id,
                                    name: "api_build_tool",
                                    output_types: ["Tool"],
                                },
                            },
                            className: "",
                            selected: false,
                        };
                    }),
                    // Add edges to connect the subagents to the AI agent node
                    ...subagentEdges,
                ],
                viewport: defaultViewport, // Add this line to fix the error
            },
        };

        if (fileCategories[0].files.length > 0) {
            try {
                createCollectionInMilvus(collectionName);
                insertFilesIntoDatabase(fileCategories, collectionName);
            } catch (error) {
                console.error('Error during the file ingestion process:', error);
            }
        }

        const axiosTriggers = axios.create({
            baseURL: '/api/v1',
            headers: useIntegrationStore.getState().getAuthHeaders(),
            withCredentials: true
        });

        // Save the updated flow and setup triggers
        addFlow({ flow: updatedFlow, override: false }).then((flowId) => {
            // Setup triggers for the new flow using the flowId
            for (const triggerId of selectedTriggers) {
                try {
                    // First call - Watch Gmail with query parameters
                    axiosTriggers.post(`/gmail/watch/${triggerId}?integration_id=${triggerId}&flow_id=${flowId}`);

                    // Second call - Create integration trigger
                    axiosTriggers.post(`/integrations/trigger?integration_id=${triggerId}&flow_id=${flowId}`);
                } catch (error) {
                    console.error('Failed to setup trigger:', triggerId, error);
                }
            }

            // Navigate to the new flow
            navigate(
                `/flow/${flowId}${folderId ? `/folder/${folderId}` : ""}`,
            );
        });

        //track("New Flow Created", { template: "Guided Agent" });
    };

    // Define categories and their items
    const tabCategories: Category[] = [
        {
            title: "Agent Builder",
            items: [
                { title: "Basic informations", icon: "Bot", id: "guided-ai-agent" },
                //{ title: "All templates", icon: "LayoutPanelTop", id: "all-templates" },
            ],
        },
        {
            title: "Agent insctructions",
            items: [
                { title: "Core instructions", icon: "Newspaper", id: "core-instructions" },
                { title: "Flow builder", icon: "workflow", id: "flow-builder" },
            ],
        },
        {
            title: "Connected resources",
            items: [
                // { title: "Integrations", icon: "sparkles", id: "integrations" },
                { title: "knowledge", icon: "Database", id: "khowledge_base" },
                { title: "Tools", icon: "hammer", id: "tools-link" },
                { title: "Subagents", icon: "git-fork", id: "subagents" },
                { title: "Triggers", icon: "clock", id: "triggers" },
            ],
        },

        {
            title: "More settings",
            items: [
                { title: "Advanced options", icon: "settings", id: "advanced-settings" },
                // { title: "Configure template", icon: "layout-panel-top", id: "configure-template" },
                // { title: "Task views", icon: "list-todo", id: "agentss" },
            ],
        }
    ];

    const defaultViewport: Viewport = { x: 5, y: 15, zoom: 1 };


    return (
        <GuidedAgentModal size="x-large" open={open} setOpen={setOpen} className="p-0">
            <GuidedAgentModal.Content overflowHidden className="flex flex-col p-0">
                <div className="flex h-full">
                    <SidebarProvider width="15rem" defaultOpen={false}>
                        <GuidedAgentNavComponent
                            categories={tabCategories}
                            currentTab={currentTab}
                            setCurrentTab={setCurrentTab}
                            agentName={name}
                        />
                        <main className="flex flex-1 flex-col gap-4 overflow-hidden p-6 md:gap-8">
                            {currentTab === "guided-ai-agent" ? (
                                <CreateAIAgentComponent
                                    name={name}
                                    setName={setName}
                                    description={description}
                                    setDescription={setDescription}
                                /> // Render the CreateAIAgentComponent when currentTab is "AI Agent"
                            ) : currentTab === "core-instructions" ? (
                                <GuidedAiAgentCoreInstructions
                                    prompt={prompt}
                                    setPrompt={setPrompt}
                                />
                            ) : currentTab === "flow-builder" ? (
                                <div ref={reactFlowWrapper} style={{ height: 600 }}>
                                    {nodes.length > 1 ? (<ReactFlow
                                        nodes={nodes.map((node) => ({
                                            ...node,
                                            data: {
                                                ...node.data,
                                                onAddNode: (nodeType) => handleAddNode(node.id, nodeType), // Add dynamic onAddNode handler
                                                onInputChange: (newValue) => handleInputChange(node.id, newValue),
                                                onDeleteNode: () => handleDeleteNode(node.id),
                                            },
                                        }))}
                                        edges={edges}
                                        onNodesChange={onNodesChange}
                                        onEdgesChange={onEdgesChange}
                                        nodesDraggable={false}
                                        nodeTypes={nodeTypes}
                                        panOnScroll
                                        panOnDrag={panOnDrag}
                                        selectionMode={SelectionMode.Partial}
                                        onConnect={onConnect}
                                        colorMode="light"
                                        fitView
                                    >
                                        <Background />
                                        <Panel position="top-left">
                                            <div className={styles.wrapperStyle}>
                                                <button onClick={handleZoomIn} className={styles.buttonStyle}>
                                                    <ForwardedIconComponent name="plus" className={styles.iconControl} />
                                                </button>
                                                <button onClick={handleFitView} className={styles.buttonStyle}>
                                                    <ForwardedIconComponent name="maximize" className={styles.iconControl} />
                                                </button>
                                                <button onClick={handleZoomOut} className={styles.buttonStyle}>
                                                    <ForwardedIconComponent name="minus" className={styles.iconControl} />
                                                </button>
                                            </div>
                                        </Panel>
                                        <MiniMap nodeStrokeWidth={3} zoomable pannable />
                                    </ReactFlow>) : (<ReactFlow
                                        nodes={nodes.map((node) => ({
                                            ...node,
                                            data: {
                                                ...node.data,
                                                onAddNode: (nodeType) => handleAddNode(node.id, nodeType), // Add dynamic onAddNode handler
                                                onInputChange: (newValue) => handleInputChange(node.id, newValue),
                                                onDeleteNode: () => handleDeleteNode(node.id),
                                            },
                                        }))}
                                        edges={edges}
                                        onNodesChange={onNodesChange}
                                        onEdgesChange={onEdgesChange}
                                        nodesDraggable={false}
                                        nodeTypes={nodeTypes}
                                        panOnScroll
                                        panOnDrag={panOnDrag}
                                        selectionMode={SelectionMode.Partial}
                                        onConnect={onConnect}
                                        colorMode="light"
                                        defaultViewport={defaultViewport}
                                    >
                                        <Background />
                                        <Panel position="top-left">
                                            <div className={styles.wrapperStyle}>
                                                <button onClick={handleZoomIn} className={styles.buttonStyle}>
                                                    <ForwardedIconComponent name="plus" className={styles.iconControl} />
                                                </button>
                                                <button onClick={handleFitView} className={styles.buttonStyle}>
                                                    <ForwardedIconComponent name="maximize" className={styles.iconControl} />
                                                </button>
                                                <button onClick={handleZoomOut} className={styles.buttonStyle}>
                                                    <ForwardedIconComponent name="minus" className={styles.iconControl} />
                                                </button>
                                            </div>
                                        </Panel>
                                        <MiniMap nodeStrokeWidth={3} zoomable pannable />
                                    </ReactFlow>)}

                                </div>
                            ) : currentTab === "tools-link" ? (
                                <GuidedAgentsToolsLinkComponent
                                    addTool={handleAddTool}
                                    addedTools={addedTools}
                                    deleteTool={handleDeleteTool}
                                />
                            ) : currentTab === "khowledge_base" ? (
                                <KhownledgeBaseFilesUpload
                                    fileCategories={fileCategories}
                                    setFileCategories={setFileCategories}
                                    activeCategory={activeCategory} // Pass activeCategory as a prop
                                    setActiveCategory={setActiveCategory} // Pass setActiveCategory as a prop
                                    onFilesUpdate={handleFilesUpdate}
                                />
                            ) : currentTab === "integrations" ? (
                                <GuidedAgentIntegrations />
                            ) : currentTab === "triggers" ? (
                                <GuidedAgentTriggers
                                    onTriggersChange={handleTriggersChange}
                                    selectedTriggers={selectedTriggers}
                                    setSelectedTriggers={setSelectedTriggers}
                                />
                            ) : currentTab === "advanced-settings" ? (
                                <GuidedAgentAIAgentAdvancedSettings
                                    settings={advancedSettings}
                                    onSettingsChange={setAdvancedSettings}
                                />
                            ) : currentTab === "subagents" ? (
                                <GuidedAgentSubagents
                                    addedSubagents={addedSubagents}
                                    addSubagent={handleAddSubagent}
                                    deleteSubagent={handleDeleteSubagent}
                                />
                            ) : (
                                <TemplateContentComponent
                                    currentTab={currentTab}
                                    categories={tabCategories.flatMap((category) => category.items)}
                                />
                            )}
                            <GuidedAgentModal.Footer>
                                <div className="flex w-full flex-col justify-between gap-4 pb-4 sm:flex-row sm:items-center">
                                    <div className="flex flex-col items-start justify-center">
                                        <div className="font-semibold">Launch your AI Agent</div>
                                        <div className="text-sm text-muted-foreground">
                                            Configure your agent's behavior, knowledge, and capabilities
                                        </div>
                                    </div>
                                    <Button
                                        onClick={handleCreate}
                                        size="sm"
                                        data-testid="blank-flow"
                                        className="shrink-0"
                                    >
                                        <ForwardedIconComponent
                                            name="Plus"
                                            className="h-4 w-4 shrink-0"
                                        />
                                        Create
                                    </Button>
                                </div>
                            </GuidedAgentModal.Footer>
                        </main>
                    </SidebarProvider>
                </div>
            </GuidedAgentModal.Content>
            <GuidedAgentForm open={isGuidedAgentFormOpen} setOpen={setIsGuidedAgentFormOpen} />
        </GuidedAgentModal>
    );
}