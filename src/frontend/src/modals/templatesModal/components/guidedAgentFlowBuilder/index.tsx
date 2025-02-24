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
} from '@xyflow/react';
import { v4 as uuidv4 } from 'uuid';
import InstructionNode from './CustomNode';

const nodeTypes = { InstructionNode: InstructionNode };

const initialNodes = [
    {
        id: '1',
        type: 'InstructionNode',
        position: { x: 250, y: 0 },
        data: {
            label: 'Start Node',
            onAddNode: (event) => {},
        },
    },
];
const panOnDrag = [1, 2];

export default function InteractionFlow() {
    const reactFlowWrapper = useRef(null);
    const { screenToFlowPosition } = useReactFlow();

    const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
    const [edges, setEdges, onEdgesChange] = useEdgesState<Edge<any>>([]);

    const handleClickToAddNode = (nodeId, event) => {
        document.removeEventListener('click', () => handleClickToAddNode(nodeId, event)); // Clean up
        handleAddNode(nodeId, event);
    };

    const handleAddNode = useCallback(
        (originNodeId, event) => {
            const originNode = nodes.find((node) => node.id === originNodeId);
            if (!originNode) return;

            const id = uuidv4();
            const newNode = {
                id,
                type: 'InstructionNode',
                position: { x: originNode.position.x, y: originNode.position.y + 300 },
                data: {
                    label: `New Node ${id}`,
                    onAddNode: (e) => handleAddNode(id, e),
                },
            };

            const childEdge = edges.find((edge) => edge.source === originNodeId);
            const childId = childEdge?.target;
            const childNode = nodes.find((node) => node.id === childId);

            if (childNode) {
                childNode.position.x += 10;
            }

            const offset = 300;
            const updatedNodes = nodes.map((node) =>
                node.position.y > originNode.position.y
                    ? { ...node, position: { ...node.position, y: node.position.y + offset } }
                    : node
            );

            setNodes((prevNodes) => [...updatedNodes, newNode]);

            const newEdges = edges
                .filter((edge) => edge.source !== originNodeId || edge.target !== childId)
                .concat(
                    { id: `e${originNodeId}-${id}`, source: originNodeId, target: id, type: 'default' },
                    childId ? { id: `e${id}-${childId}`, source: id, target: childId, type: 'default' } : []
                );

            setEdges(newEdges);
        },
        [nodes, edges, setNodes, setEdges]
    );

    return (
        <div ref={reactFlowWrapper} style={{ height: 600 }}>
            <ReactFlow
                nodes={nodes.map((node) => ({
                    ...node,
                    data: {
                        ...node.data,
                        onAddNode: (event) => handleClickToAddNode(node.id, event),
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
            >
                <Background />
                <Controls />
            </ReactFlow>
        </div>
    );
};
