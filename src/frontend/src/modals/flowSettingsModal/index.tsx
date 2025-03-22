import useSaveFlow from "@/hooks/flows/use-save-flow";
import useAlertStore from "@/stores/alertStore";
import useFlowStore from "@/stores/flowStore";
import useFlowsManagerStore from "@/stores/flowsManagerStore";
import { cloneDeep } from "lodash";
import { useCallback, useEffect, useRef, useState } from "react";
import IconComponent, { ForwardedIconComponent } from "../../components/common/genericIconComponent";
import EditFlowSettings from "../../components/core/editFlowSettingsComponent";
import { SETTINGS_DIALOG_SUBTITLE } from "../../constants/constants";
import { FlowSettingsPropsType } from "../../types/components";
import { AllNodeType, FlowType } from "../../types/flow";
import { isEndpointNameValid } from "../../utils/utils";
import BaseModal from "../baseModal";
import { useFlowWizardMetadata } from "@/hooks/flows/use-flow-wizard-metadata";
import { useIntegrationStore } from "@/stores/integrationStore";
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
import { handleDeleteNode, handleInputChange, handleAddNode, transformFlowToPrompt } from "./reactFlowUtils";
import { insertFile, deleteFileFromDatabase, insertFilesIntoDatabase } from "./fileUtils";

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
  const setCurrentFlowInManager = useFlowsManagerStore((state) => state.setCurrentFlow);
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
      position: { x: 400, y: 0 },
      data: {
        label: 'Start Node',
        instruction: '', // Placeholder for user input
        onAddNode: (nodeType) => handleAddNode('1', nodeType, nodes, edges, setNodes, setEdges), // Dynamically handle node addition
        onInputChange: (nodeId, newValue) => handleInputChange(nodeId, newValue, setNodes), // Handle input changes
        onDeleteNode: () => handleDeleteNode('1', nodes, edges, setNodes, setEdges), // Dynamically handle node deletion
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

  // Function to update the flow JSON with wizard metadata
  const updateFlowWithWizardMetadata = (flow: FlowType): FlowType => {
    if (!flow || !flow.data || !flow.data.nodes) {
      console.error("Invalid flow data");
      return flow;
    }

    // Generate prompt from flow builder if needed
    let agentInstuctions = prompt;
    if (nodes.length > 1) {
      const generatedPrompt = transformFlowToPrompt(nodes, edges);
      agentInstuctions = agentInstuctions + "\n\n" + generatedPrompt + "\n\nRULES:\n1. Never query the Vector Store with an empty string.\n2. If you don't know the answer, just say so. Don't make up an answer.\n3. If you are unsure about the answer, just say so. Don't make up an answer.";
    } else if (!prompt) {
      agentInstuctions = "You are a helpful assistant that can answer questions and help with tasks." + "\n\nRULES:\n1. Never query the Vector Store with an empty string.\n2. If you don't know the answer, just say so. Don't make up an answer.\n3. If you are unsure about the answer, just say so. Don't make up an answer.";
    }

    // Create a deep copy of the flow to avoid mutating the original
    const updatedFlow = { ...flow, data: { ...flow.data, nodes: [...flow.data.nodes], edges: [...flow.data.edges] } };
    
    // Collection name for vector store
    const collectionName = wizardMetadata?.collectionName || `agent_KB_${Math.random().toString(36).substr(2, 9)}`;

    // Define a type for generic nodes to avoid TypeScript errors
    type GenericNodeType = {
      id: string;
      type: string;
      position: { x: number; y: number };
      data: {
        node: any;
        showNode: boolean;
        type: string;
        id: string;
      };
      selected?: boolean;
      measured?: {
        width: number;
        height: number;
      };
      dragging?: boolean;
    };

    // Find the agent node (usually OpenAIToolsAgent or similar)
    const agentNode = updatedFlow.data.nodes.find(node => 
      node.data?.type === "ToolCallingAgent" || 
      node.data?.type === "OpenAIToolsAgent" ||
      node.data?.id?.includes("OpenAIToolsAgent")
    );
    
    // If we don't have an agent node, we can't add tools or subagents
    if (!agentNode) {
      console.warn("No agent node found in the flow, can't add tools or subagents");
      return updatedFlow;
    }

    // Get the current tools and subagents from the wizard metadata
    const currentToolNames = wizardMetadata?.tools?.map(tool => tool.display_name) || [];
    const currentSubagentNames = wizardMetadata?.subagents?.map(subagent => subagent.name) || [];

    // Get the new tools and subagents from the user inputs
    const newToolNames = addedTools.map(tool => tool.display_name);
    const newSubagentNames = addedSubagents.map(subagent => subagent.name);

    // Find tools to add and remove
    const toolsToAdd = addedTools.filter(tool => !currentToolNames.includes(tool.display_name));
    const toolsToRemove = currentToolNames.filter(toolName => !newToolNames.includes(toolName));

    // Find subagents to add and remove
    const subagentsToAdd = addedSubagents.filter(subagent => !currentSubagentNames.includes(subagent.name));
    const subagentsToRemove = currentSubagentNames.filter(subagentName => !newSubagentNames.includes(subagentName));

    console.log("Tools to add:", toolsToAdd.map(t => t.display_name));
    console.log("Tools to remove:", toolsToRemove);
    console.log("Subagents to add:", subagentsToAdd.map(s => s.name));
    console.log("Subagents to remove:", subagentsToRemove);

    // Identify existing tool nodes in the flow
    const existingToolNodes = updatedFlow.data.nodes.filter(node => {
      // Check if this is a tool node
      if (!node.data?.type) return false;

      // Skip core components that are not tools
      if (
        node.data.type === "OpenAIToolsAgent" ||
        node.data.type === "ToolCallingAgent" ||
        node.data.type === "OpenAIModel" ||
        node.data.type === "Prompt" ||
        node.data.type === "OpenAIEmbeddings" ||
        node.data.type === "Milvus" ||
        node.data.type === "ChatMessage" ||
        node.data.type === "ChatMessagePromptTemplate" ||
        node.data.type === "ChatInput" ||
        node.data.type === "ChatOutput" ||
        node.data.type === "Memory" ||
        node.data.type === "RunFlow"
      ) {
        return false;
      }

      return true;
    });
    
    // Identify existing subagent nodes in the flow
    const existingSubagentNodes = updatedFlow.data.nodes.filter(node => 
      node.data?.type === "RunFlow" || 
      (node.data?.id && node.data.id.includes("RunFlow"))
    );

    // Find tool nodes to remove based on the tool names to remove
    const toolNodesToRemove = existingToolNodes.filter(node => {
      // Extract the tool name from the node
      const toolName = node.data?.node?.display_name;
      return toolName && toolsToRemove.includes(toolName);
    });

    // Find subagent nodes to remove based on the subagent names to remove
    const subagentNodesToRemove = existingSubagentNodes.filter(node => {
      // Extract the subagent name from the node
      const subagentName = node.data?.node?.template?.flow_name_selected?.value;
      return subagentName && subagentsToRemove.includes(subagentName);
    });

    // Get the IDs of nodes to remove
    const nodeIdsToRemove = [
      ...toolNodesToRemove.map(node => node.id),
      ...subagentNodesToRemove.map(node => node.id)
    ];

    // Find edges connected to the nodes to remove
    const edgesToRemove = updatedFlow.data.edges.filter(edge => {
      // Check if the edge connects to a node that is being removed
      return nodeIdsToRemove.includes(edge.source) || nodeIdsToRemove.includes(edge.target);
    });

    // Get the IDs of edges to remove
    const edgeIdsToRemove = edgesToRemove.map(edge => edge.id);

    // Create new tool nodes for tools to add
    const toolNodes: GenericNodeType[] = toolsToAdd.map((tool, index) => {
      const toolId = `${tool.display_name.replace(/\s+/g, '')}-${Math.random().toString(36).substr(2, 7)}`;

      // Handle special cases for certain tools
      if (tool.display_name === "Gmail Fetcher Tool" || 
          tool.display_name === "Gmail Sender Tool" || 
          tool.display_name === "Gmail Responder Tool" || 
          tool.display_name === "Gmail Draft Tool") {
        tool.template.api_key = {
          ...tool.template.api_key,
          value: "m1m8sy261xzb4l4hjmwq",
          load_from_db: false
        };
      }

      // Handle integration tools that need user_id
      if (tool.display_name === "Gmail Email Loader" || 
          tool.display_name === "Gmail Email Sender" || 
          tool.display_name === "Gmail Email Responder" ||
          tool.display_name === "Gmail Email Draft Creator" ||
          tool.display_name === "Google Calendar Event Creator" ||
          tool.display_name === "Google Calendar Event Loader" ||
          tool.display_name === "Google Calendar Event Modifier" ||
          tool.display_name === "Google Sheets Data Loader" ||
          tool.display_name === "Google Sheets Data Modifier" ||
          tool.display_name === "Slack Message Sender" ||
          tool.display_name === "Slack Retrieve Messages" ||
          tool.display_name === "Slack List Channels & Users" ||
          tool.display_name === "Slack DM Sender" ||
          tool.display_name === "HubSpot Contact Creator" ||
          tool.display_name === "HubSpot Deal Creator" ||
          tool.display_name === "HubSpot Company Creator" ||
          tool.display_name === "HubSpot Company Loader" ||
          tool.display_name === "HubSpot Contact Loader") {
        // Get the access token from cookies
        const token = document.cookie
          .split('; ')
          .find(row => row.startsWith('access_token_lf='))
          ?.split('=')[1];

        if (token) {
          // Decode the JWT to get the user ID
          const base64Url = token.split('.')[1];
          const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
          const jsonPayload = decodeURIComponent(atob(base64).split('').map(function (c) {
            return '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2);
          }).join(''));

          const { sub: user_id } = JSON.parse(jsonPayload);
          
          // Set the user_id in the tool template
          if (tool.template && tool.template.user_id) {
            tool.template.user_id = {
              ...tool.template.user_id,
              value: user_id
            };
          }
        }
      }

      return {
        id: toolId,
        type: "genericNode",
        position: { x: 200 * (index + 1), y: 100 },
        data: {
          node: tool,
          showNode: !tool.minimized,
          type: tool.display_name,
          id: toolId,
        },
      };
    });

    // Get all flow names for subagent selection
    const userFlowNames = flows?.map((f) => f.name) || [];

    // Create nodes for subagents to add
    const subagentNodes: GenericNodeType[] = subagentsToAdd.map((subagent, index) => {
      const subagentNodeId = `RunFlow-${Math.random().toString(36).substring(2, 7)}`;
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
                "options": userFlowNames,
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
      const agentNodeId = agentNode?.id || '';
      
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

    // Create edges for the tool nodes
    const toolEdges = toolNodes.map((toolNode) => {
      const sourceHandle = `{œdataTypeœ:œ${toolNode.data.type}œ,œidœ:œ${toolNode.id}œ,œnameœ:œapi_build_toolœ,œoutput_typesœ:[œToolœ]}`;
      const targetHandle = `{œfieldNameœ:œtoolsœ,œidœ:œ${agentNode?.id || ''}œ,œinputTypesœ:[œToolœ],œtypeœ:œotherœ}`;

      return {
        id: `xy-edge__${toolNode.id}${sourceHandle}-${agentNode?.id || ''}${targetHandle}`,
        source: toolNode.id,
        target: agentNode?.id || '',
        sourceHandle: sourceHandle,
        targetHandle: targetHandle,
        data: {
          targetHandle: {
            fieldName: "tools",
            id: agentNode?.id || '',
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
    });

    // Update the nodes in the flow
    updatedFlow.data.nodes = updatedFlow.data.nodes.map((node): any => {
      // Update the prompt node with the new instructions
      if (node.data?.id?.includes("Prompt")) {
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
        };
      }

      // Update the OpenAI model node with advanced settings
      if (node.data?.type === "OpenAIModel") {
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
        };
      }

      // Update the Milvus node with the collection name
      if (node.data?.id?.includes("Milvus")) {
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
        };
      }

      // Update the OpenAI embeddings model
      if (node.data?.id?.includes("OpenAIEmbeddings")) {
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
        };
      }

      // Update the OpenAI tools agent with advanced settings
      if (node.data?.id?.includes("OpenAIToolsAgent")) {
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
        };
      }

      return node;
    });

    // Remove nodes that need to be removed
    updatedFlow.data.nodes = updatedFlow.data.nodes.filter(node => {
      // Keep the node if it's not in the list of nodes to remove
      return !nodeIdsToRemove.includes(node.id);
    });

    // Remove edges connected to the removed nodes
    updatedFlow.data.edges = updatedFlow.data.edges.filter(edge => {
      // Keep the edge if it's not in the list of edges to remove
      return !edgeIdsToRemove.includes(edge.id);
    });

    // Add the new tool and subagent nodes
    const allNodes = [
      ...updatedFlow.data.nodes,
      ...toolNodes,
      ...subagentNodes
    ];
    
    // Type assertion to satisfy TypeScript
    updatedFlow.data.nodes = allNodes as AllNodeType[];

    // Add the new edges
    updatedFlow.data.edges = [
      ...updatedFlow.data.edges,
      ...toolEdges,
      ...subagentEdges
    ];

    return updatedFlow;
  };

  const handleUpdate = async () => {
    setIsSaving(true);
    try {
      // Generate prompt from flow builder if needed
      if (nodes.length > 1) {
        const generatedPrompt = transformFlowToPrompt(nodes, edges);
        setPrompt(generatedPrompt);
      }

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

        // Update the flow with wizard metadata
        const updatedFlow = updateFlowWithWizardMetadata(flowData);

        // Use provided onUpdate function or fallback to saveFlow
        if (onUpdate) {
          await onUpdate(name, description, updatedFlow.id, endpoint_name);
        } else {
          // Use the saveFlow hook as a fallback
          await saveFlow({
            ...updatedFlow,
            name,
            description,
            endpoint_name
          });
        }

        // Handle triggers - compare current triggers with selected triggers
        try {
          // Get the current triggers from the wizard metadata
          const currentTriggers = wizardMetadata?.triggers || [];
          
          // Find triggers to add and remove
          const triggersToAdd = selectedTriggers.filter(trigger => !currentTriggers.includes(trigger));
          const triggersToRemove = currentTriggers.filter(trigger => !selectedTriggers.includes(trigger));
          
          console.log("Triggers to add:", triggersToAdd);
          console.log("Triggers to remove:", triggersToRemove);

          // Create axios instance for trigger API calls
          const axiosTriggers = axios.create({
            baseURL: '/api/v1',
            headers: useIntegrationStore.getState().getAuthHeaders(),
            withCredentials: true
          });

          // Handle triggers to remove - unwatch webhooks and delete trigger entries
          for (const triggerInfo of triggersToRemove) {
            try {
              // Parse the trigger info (format: "service_name:integration_id")
              const [serviceName, integrationId] = triggerInfo.split(':');
              
              // Call the appropriate unwatch endpoint based on the service name
              if (serviceName === 'gmail') {
                // For Gmail, we need to call stop on the users endpoint
                await axiosTriggers.post(`/gmail/watch/${integrationId}`, {
                  integration_id: integrationId,
                  flow_id: flowData.id
                });
                // Delete integration trigger - DELETE to /integrations/trigger
                await axiosTriggers.delete(`/integrations/trigger/${integrationId}/${flowData.id}`);
              } else if (serviceName === 'slack') {
                // For Slack, use POST method to unwatch
                await axiosTriggers.post(`/slack/unwatch/${integrationId}`, {
                  integration_id: integrationId,
                  flow_id: flowData.id
                });
                // Delete integration trigger
                await axiosTriggers.delete(`/integrations/trigger/${integrationId}/${flowData.id}`);
              } else if (serviceName === 'hubspot') {
                // For HubSpot, use POST to unwatch
                await axiosTriggers.post(`/hubspot/unwatch/${integrationId}`, {
                  integration_id: integrationId,
                  flow_id: flowData.id
                });
                // Delete integration trigger
                await axiosTriggers.delete(`/integrations/trigger/${integrationId}/${flowData.id}`);
              }
            } catch (error) {
              console.error('Failed to remove trigger:', triggerInfo, error);
              // Continue with other triggers even if one fails
            }
          }

          // Handle triggers to add - set up webhooks and create trigger entries
          for (const triggerInfo of triggersToAdd) {
            try {
              // Parse the trigger info (format: "service_name:integration_id")
              const [serviceName, integrationId] = triggerInfo.split(':');
              
              // Call the appropriate watch endpoint based on the service name
              if (serviceName === 'gmail') {
                axiosTriggers.post(`/gmail/watch/${integrationId}?integration_id=${integrationId}&flow_id=${flowData.id}`);
                // Create integration trigger
                axiosTriggers.post(`/integrations/trigger?integration_id=${integrationId}&flow_id=${flowData.id}`);
              } else if (serviceName === 'slack') {
                // For Slack, use POST to watch
                axiosTriggers.post(`/slack/watch/${integrationId}`);
                // Create integration trigger
                axiosTriggers.post(`/integrations/trigger?integration_id=${integrationId}&flow_id=${flowData.id}`);
              } else if (serviceName === 'hubspot') {
                // Create integration trigger for HubSpot
                axiosTriggers.post(`/create-integration-trigger/hubspot?integration_id=${integrationId}&flow_id=${flowData.id}`);
                // Set up HubSpot webhook for deal events
                axiosTriggers.post(`/hubspot/watch/${integrationId}`);
              }
            } catch (error) {
              console.error('Failed to setup trigger:', triggerInfo, error);
              // Continue with other triggers even if one fails
            }
          }
        } catch (error) {
          console.error("Error managing triggers:", error);
          // Continue with the flow update even if trigger management fails
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
        
        // Create updated flow data
        const updatedFlowData = {
          ...updatedFlow,
          name,
          description,
          endpoint_name
        };
        
        // Update the FlowsManagerStore which will update both currentFlow and currentFlowId
        setCurrentFlowInManager(updatedFlowData);
        
        // Show success message
        setSuccessData({
          title: "Flow updated successfully",
        });

        // Close the modal
        setOpen(false);
      }
    } catch (error) {
      console.error("Error updating flow:", error);
      setErrorData({
        title: "Error updating flow",
        list: [(error as Error).message || "An unknown error occurred"],
      });
    } finally {
      setIsSaving(false);
    }
  };

  // Define categories and their items for the wizard sidebar
  const tabCategories: Category[] = [
    {
      title: "Agent Builder",
      items: [
        { title: "Basic informations", icon: "Bot", id: "guided-ai-agent" },
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
                        onAddNode: (nodeType) => handleAddNode(node.id, nodeType, nodes, edges, setNodes, setEdges), // Add dynamic onAddNode handler
                        onInputChange: (newValue) => handleInputChange(node.id, newValue, setNodes),
                        onDeleteNode: () => handleDeleteNode(node.id, nodes, edges, setNodes, setEdges),
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
                        onAddNode: (nodeType) => handleAddNode(node.id, nodeType, nodes, edges, setNodes, setEdges), // Add dynamic onAddNode handler
                        onInputChange: (newValue) => handleInputChange(node.id, newValue, setNodes),
                        onDeleteNode: () => handleDeleteNode(node.id, nodes, edges, setNodes, setEdges),
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
                  activeAgent={flow?.id ?? null}
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