import useSaveFlow from "@/hooks/flows/use-save-flow";
import useAlertStore from "@/stores/alertStore";
import useFlowStore from "@/stores/flowStore";
import { cloneDeep } from "lodash";
import { useCallback, useEffect, useRef, useState } from "react";
import IconComponent, { ForwardedIconComponent } from "../../components/common/genericIconComponent";
import EditFlowSettings from "../../components/core/editFlowSettingsComponent";
import { SETTINGS_DIALOG_SUBTITLE } from "../../constants/constants";
import useFlowsManagerStore from "../../stores/flowsManagerStore";
import { FlowSettingsPropsType } from "../../types/components";
import { FlowType } from "../../types/flow";
import { isEndpointNameValid } from "../../utils/utils";
import BaseModal from "../baseModal";
import { useFlowWizardMetadata } from "@/hooks/flows/use-flow-wizard-metadata";
import { SidebarProvider } from "@/components/ui/sidebar";
import { GuidedAgentNavComponent } from "../templatesModal/components/GuidedAgentNavComponent";
import GuidedAiAgentCoreInstructions from "../templatesModal/components/GuidedAiAgentCoreInstructions";
import { GuidedAgentsToolsLinkComponent } from "../templatesModal/components/GuidedAgentToolsLinkComponent";
import KhownledgeBaseFilesUpload from "../templatesModal/components/GuidedAgentkhowledgeBase";
import GuidedAgentSubagents from "../templatesModal/components/GuidedAgentSubagents";
import GuidedAgentTriggers from "../templatesModal/components/GuidedAgentTriggers";
import GuidedAgentAIAgentAdvancedSettings from "../templatesModal/components/GuidedAgentAIAgentAdvancedSettings";
import { Background, Edge, Panel, ReactFlowProvider, SelectionMode, useEdgesState, useNodesState, useReactFlow } from "@xyflow/react";
import { v4 as uuidv4 } from 'uuid';
import { FileCategory, FileItem } from "../templatesModal/components/GuidedAgentkhowledgeBase/types";
import GuidedAgentModal from "../guidedAgentModal";
import CreateAIAgentComponent from "../templatesModal/components/CreateGuidedAIAgentComponent";
import {
  ReactFlow,
  Controls,
  MiniMap,
  Viewport
} from '@xyflow/react';
import GuidedAgentIntegrations from "../templatesModal/components/GuidedAgentIntegrations";
import TemplateContentComponent from "../templatesModal/components/TemplateContentComponent";
import GuidedAgentForm from "@/components/core/guidedagentform";
import ConditionNode from "../templatesModal/components/guidedAgentFlowBuilder/conditionNode";
import InstructionNode from "../templatesModal/components/guidedAgentFlowBuilder/CustomNode";
import StartPointNode from "../templatesModal/components/guidedAgentFlowBuilder/startPointNode";
import { Button } from "@/components/ui/button";
import { Category } from "@/types/templates/types";
import axios from "axios";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";

export default function FlowSettingsModal({
  open,
  setOpen,
  flowData,
  nameLists,
  onUpdate,
}: {
  open: boolean;
  setOpen: (open: boolean) => void;
  flowData?: FlowType;
  nameLists: string[];
  onUpdate?: (
    name: string,
    description: string,
    flow_id: string,
    endpoint_name?: string
  ) => Promise<void>;
}) {
  const saveFlow = useSaveFlow();
  const currentFlow = useFlowStore((state) => state.currentFlow);
  const setCurrentFlow = useFlowStore((state) => state.setCurrentFlow);
  const setSuccessData = useAlertStore((state) => state.setSuccessData);
  const setErrorData = useAlertStore((state) => state.setErrorData);
  const flows = useFlowsManagerStore((state) => state.flows);

  // Ensure flowData is defined by using nullish coalescing with an empty object
  const flow = flowData ?? currentFlow;
  useEffect(() => {
    setName(flow?.name ?? "");
    setDescription(flow?.description ?? "");
  }, [flow?.name, flow?.description, open]);
  const [flowedges, setflowedges] = useEdgesState<Edge<any>>([]);
  // Initialize state with safe values
  const [name, setName] = useState(flowData?.name || "");
  const [description, setDescription] = useState(flowData?.description || "");
  const [endpoint_name, setEndpointName] = useState(flowData?.endpoint_name || "");
  const [isSaving, setIsSaving] = useState(false);
  const [disableSave, setDisableSave] = useState(true);
  const autoSaving = useFlowsManagerStore((state) => state.autoSaving);

  // Wizard metadata state
  const [prompt, setPrompt] = useState("");
  const [collectionName, setCollectionName] = useState("");
  const [currentTab, setCurrentTab] = useState("guided-ai-agent");
  const [addedTools, setAddedTools] = useState<any[]>([]);
  const [addedSubagents, setAddedSubagents] = useState<any[]>([]);
  const [selectedTriggers, setSelectedTriggers] = useState<string[]>([]);
  const [fileCategories, setFileCategories] = useState<FileCategory[]>([
    { id: 'default', name: 'General', files: [] }
]);
  const [activeCategory, setActiveCategory] = useState('default');
  const [fileToDelete, setFileToDelete] = useState<string | null>(null);
  const [isDeleteDialogOpen, setIsDeleteDialogOpen] = useState(false);
  type AdvancedSettings = {
    temperature: number;
    modelName: string;
    maxRetries: number;
    timeout: number;
    seed: number;
    jsonMode: boolean;
    maxTokens: number;
    handleParseErrors: boolean;
  };
  const [advancedSettings, setAdvancedSettings] = useState<AdvancedSettings>({
    temperature: 0.3,
    modelName: "gpt-3.5-turbo",
    maxRetries: 10,
    timeout: 700,
    seed: 1,
    jsonMode: false,
    maxTokens: 0,
    handleParseErrors: true
  });

  // Flow builder state
  const nodeTypes = {
    InstructionNode: InstructionNode,
    ConditionNode: ConditionNode,
    StartPointNode: StartPointNode,
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
  const [isGuidedAgentFormOpen, setIsGuidedAgentFormOpen] = useState(false);

  const panOnDrag = [1, 2];
  const reactFlowWrapper = useRef<HTMLDivElement>(null);
  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge<any>>([]);
  const [showMenu, setShowMenu] = useState(false);
  const [menuPosition, setMenuPosition] = useState({ x: 0, y: 0 });
  const [currentNodeId, setCurrentNodeId] = useState<string | null>(null);
  const defaultViewport = { x: 0, y: 0, zoom: 1 };

  const { zoomIn, zoomOut, fitView } = useReactFlow();

  const handleZoomIn = useCallback(() => zoomIn(), [zoomIn]);
  const handleZoomOut = useCallback(() => zoomOut(), [zoomOut]);
  const handleFitView = useCallback(() => fitView(), [fitView]);
  const axiosInstance = axios.create({
    baseURL: 'http://localhost:3000/api/v1', 
    headers: {
      'Content-Type': 'application/json',
    },
    timeout: 120000,
  });

  const handleAddTool = (tool: any) => {
    // Check if tool is already added by comparing display_name
    const isToolAlreadyAdded = addedTools.some(
      addedTool => addedTool.display_name === tool.display_name
    );

    if (!isToolAlreadyAdded) {
      setAddedTools(prev => [...prev, tool]);
    }
  };

  // Callback to delete a tool:
  const handleDeleteTool = (tool: any) => {
    setAddedTools(prevTools =>
      prevTools.filter(t => t.display_name !== tool.display_name)
    );
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
    function isValidBase64(base64String: string): boolean {
      const base64Regex = /^[A-Za-z0-9+/]+={0,2}$/;
      return base64String.length % 4 === 0 && base64Regex.test(base64String);
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

  async function insertFilesIntoDatabase(fileCategories: FileCategory[], collectionName: string) {
    const files: FileItem[] = [];
    fileCategories.forEach((cat) => {
      files.push(...cat.files);
    });
    // Process files with a concurrency limit of 4 (adjust as needed)
    await processInBatches(files, (file) => insertFile(file, collectionName), 4);
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

  async function deleteFileFromDatabase(fileId: string, collectionName: string) {
    try {
      // Call the backend API to delete the file from Milvus
      const { data } = await axiosInstance.delete(`/milvus/files/${collectionName}/${fileId}`);
      console.log(`File ${fileId} deleted from collection ${collectionName}:`, data);
      return true;
    } catch (error) {
      console.error(`Error deleting file ${fileId} from collection ${collectionName}:`, error);
      return false;
    }
  }

  const handleDeleteFile = async (fileId: string) => {
    if (!fileId) return;
    
    try {
      // If we have a flow ID, try to get the collection name from the wizard metadata
      let collectionName = "";
      if (flowData?.id) {
        try {
          const metadata = await getFlowWizardMetadata(flowData.id);
          collectionName = metadata?.collectionName || "";
        } catch (error) {
          console.error("Error fetching collection name:", error);
        }
      }

      // If we have a collection name, delete the file from the database
      if (collectionName) {
        await deleteFileFromDatabase(fileId, collectionName);
      }

      // Update the UI state to remove the file
      setFileCategories((prevCategories: FileCategory[]) =>
        prevCategories.map((category) => ({
          ...category,
          files: category.files.filter((file) => file.id !== fileId),
        }))
      );
    } catch (error) {
      console.error("Error deleting file:", error);
      setErrorData({
        title: "Error deleting file",
        list: [(error as Error).message || "An unknown error occurred"],
      });
    }
  };

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

  const onConnect = useCallback((params: any) => {
    setEdges((eds) => [...eds, { ...params, type: 'default' }]);
  }, [setEdges]);

  // Flow wizard metadata hook
  const {
    loading: metadataLoading,
    metadata: wizardMetadata,
    getFlowWizardMetadata,
    updateFlowWizardMetadata
  } = useFlowWizardMetadata();

  // Fetch wizard metadata when modal opens
  useEffect(() => {
    if (open && flowData && flowData.id) {
      getFlowWizardMetadata(flowData.id).then((metadata) => {
        console.log("Fetched wizard metadata:", metadata);
        if (metadata) {
          // Initialize states from metadata
          setPrompt(metadata.prompt || "");
          setCollectionName(metadata.collectionName || "");
          setAddedTools(metadata.tools || []);
          setAddedSubagents(metadata.subagents || []);
          setSelectedTriggers(metadata.triggers || []);
          setFileCategories(metadata.knowledgeBase?.categories || [{ id: 'default', name: 'General', files: [] }]);

          // Set advanced settings with defaults for any missing properties
          if (metadata.advancedSettings) {
            setAdvancedSettings({
              temperature: metadata.advancedSettings.temperature ?? 0.3,
              modelName: metadata.advancedSettings.modelName ?? "gpt-3.5-turbo",
              maxRetries: metadata.advancedSettings.maxRetries ?? 10,
              timeout: metadata.advancedSettings.timeout ?? 700,
              seed: metadata.advancedSettings.seed ?? 1,
              jsonMode: metadata.advancedSettings.jsonMode ?? false,
              maxTokens: metadata.advancedSettings.maxTokens ?? 0,
              handleParseErrors: metadata.advancedSettings.handleParseErrors ?? true
            });
          }

          // Initialize flow builder state
          if (metadata.flowBuilder) {
            setNodes(metadata.flowBuilder.nodes || []);
            setEdges(metadata.flowBuilder.edges || []);
          }
        }
      });
    }
  }, [open, flowData?.id]);

  useEffect(() => {
    if (flowData) {
      setName(flowData.name || "");
      setDescription(flowData.description || "");
      setEndpointName(flowData.endpoint_name || "");
    }
  }, [flowData]);

  // Handle update/save
  const handleUpdate = async () => {
    try {
      // First update the flow settings
      if (flowData && flowData.id) {
        // Process and save any files in the knowledge base
        if (fileCategories && fileCategories.length > 0) {
          try {
            // Get the metadata to compare files
            const metadata = await getFlowWizardMetadata(flowData.id);
            const collectionName = metadata?.collectionName || "";
            
            if (collectionName) {
              // Get existing files from metadata
              const existingFiles = metadata?.knowledgeBase?.categories?.flatMap(
                category => category.files
              ) || [];

              // Get current files from state
              const currentFiles = fileCategories.flatMap(
                category => category.files
              );

              // Find files to delete (files that exist in metadata but not in current state)
              const filesToDelete = existingFiles.filter(
                existingFile => !currentFiles.some(
                  currentFile => currentFile.id === existingFile.id
                )
              );

              // Find files to upload (files that exist in current state but not in metadata)
              const filesToUpload = currentFiles.filter(
                currentFile => !existingFiles.some(
                  existingFile => existingFile.id === currentFile.id
                )
              );

              // Delete files that are no longer present
              for (const file of filesToDelete) {
                try {
                  await deleteFileFromDatabase(file.id, collectionName);
                } catch (error) {
                  console.error(`Error deleting file ${file.id}:`, error);
                }
              }

              // Upload new files
              for (const file of filesToUpload) {
                try {
                  const tempCategory = {
                    id: 'temp',
                    name: 'temp',
                    files: [file]
                  };
                  await insertFilesIntoDatabase([tempCategory], collectionName);
                } catch (error) {
                  console.error(`Error uploading file ${file.id}:`, error);
                }
              }
            }
          } catch (error) {
            console.error("Error processing files:", error);
          }
        }

        // Use provided onUpdate function or fallback to saveFlow
        if (onUpdate) {
          await onUpdate(name, description, flowData.id, endpoint_name);
        } else {
          // Use the saveFlow hook as a fallback
          await saveFlow({
            ...flowData,
            name,
            description,
            endpoint_name
          });
        }

        // Then update the wizard metadata
        const wizardMetadataToSave = {
          prompt,
          collectionName: collectionName,
          tools: addedTools,
          subagents: addedSubagents,
          knowledgeBase: {
            categories: fileCategories
          },
          triggers: selectedTriggers,
          flowBuilder: {
            nodes,
            edges
          },
          advancedSettings,
        };

        await updateFlowWizardMetadata(flowData.id, wizardMetadataToSave);

        // Show success message
        setSuccessData({
          title: "Flow updated successfully",
        });

        // Close the modal
        setOpen(false);
      }
    } catch (error) {
      console.error("Error updating flow:", error);
      // Show error message
      setErrorData({
        title: "Error updating flow",
        list: [(error as Error).message || "An unknown error occurred"],
      });
    }
  };

  // Define categories and their items for the wizard sidebar
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

  // Callback to add a subagent
  const handleAddSubagent = (subagent: any) => {
    if (!addedSubagents.some(s => s.id === subagent.id)) {
      setAddedSubagents((prev) => [...prev, subagent]);
    }
  };

  // Callback to delete a subagent
  const handleDeleteSubagent = (subagent: any) => {
    setAddedSubagents((prev) => prev.filter((s) => s.id !== subagent.id));
  };

  // Callback for file updates in knowledge base
  const handleFilesUpdate = (files: FileItem[]) => {
    // Update the files for the active category
    setFileCategories(prev =>
      prev.map(category =>
        category.id === activeCategory
          ? { ...category, files }
          : category
      )
    );
  };

  // Callback for updating advanced settings
  const handleAdvancedSettingsChange = (settings: AdvancedSettings) => {
    setAdvancedSettings(settings);
  };

  useEffect(() => {
    if (!name || (nameLists && nameLists.includes(name) && name !== flowData?.name)) {
      setDisableSave(true);
    } else {
      setDisableSave(false);
    }
  }, [name, nameLists, flowData]);

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
              ) : currentTab === "subagents" ? (
                <GuidedAgentSubagents
                  addedSubagents={addedSubagents}
                  addSubagent={handleAddSubagent}
                  deleteSubagent={handleDeleteSubagent}
                />
              ) : currentTab === "triggers" ? (
                <GuidedAgentTriggers
                  selectedTriggers={selectedTriggers}
                  setSelectedTriggers={setSelectedTriggers}
                />
              ) : currentTab === "advanced-settings" ? (
                <GuidedAgentAIAgentAdvancedSettings
                  settings={advancedSettings}
                  onSettingsChange={handleAdvancedSettingsChange}
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
                    onClick={handleUpdate}
                    size="sm"
                    data-testid="blank-flow"
                    className="shrink-0"
                    disabled={disableSave}
                  >
                    <ForwardedIconComponent
                      name="Plus"
                      className="h-4 w-4 shrink-0"
                    />
                    {flowData?.id ? "Update" : "Create"}
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
