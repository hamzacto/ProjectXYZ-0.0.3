import { v4 as uuidv4 } from 'uuid';

export function findDescendants(nodeId, allEdges) {
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

export function findDescendantsNodes(nodeId, allEdges, allNodes) {
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

export function findAncestors(
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

export function findParentChildren(nodeId, edges, nodes) {
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

export function hasGrandparentWithMultipleChildren(
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

export function updateDescendantsY(
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
    return [...updatedNodes, newNode];
}

export function hasAncestorWithMultipleChildren(nodeId, edges) {
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

export function getMiddleXOfChildren(nodeId, allEdges, allNodes, positionNodeId) {
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
}

export function transformFlowToPrompt(nodes, edges) {
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

export function handleInputChange(nodeId, newValue, setNodes) {
    setNodes((prevNodes) =>
        prevNodes.map((node) =>
            node.id === nodeId
                ? { ...node, data: { ...node.data, instruction: newValue } }
                : node
        )
    );
}

export function handleAddNode(originNodeId, nodeType, nodes, edges, setNodes, setEdges) {
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
                onAddNode: (nodeType) => handleAddNode(id, nodeType, nodes, edges, setNodes, setEdges), // Recursive node addition handler
                onInputChange: (nodeId, newValue) => handleInputChange(nodeId, newValue, setNodes), // Input change handler
                onDeleteNode: () => handleDeleteNode(id, nodes, edges, setNodes, setEdges),
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

                const updatedNodes = updateDescendantsY(newNode, originNodeId, edges, nodes, 300);
                setNodes(updatedNodes);
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
                    onAddNode: (nodeType) => handleAddNode(id, nodeType, nodes, edges, setNodes, setEdges), // Recursive node addition handler
                    onInputChange: (nodeId, newValue) => handleInputChange(nodeId, newValue, setNodes), // Input change handler,
                    onDeleteNode: () => handleDeleteNode(id, nodes, edges, setNodes, setEdges),
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

                const updatedNodes = updateDescendantsY(newConditionNode, originNodeId, edges, nodes, 300);
                setNodes(updatedNodes);
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
                    onAddNode: (nodeType) => handleAddNode(id, nodeType, nodes, edges, setNodes, setEdges), // Recursive node addition handler
                    onInputChange: (nodeId, newValue) => handleInputChange(nodeId, newValue, setNodes), // Input change handler
                    onDeleteNode: () => handleDeleteNode(id, nodes, edges, setNodes, setEdges),
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
}

export function handleDeleteNode(nodeId, nodes, edges, setNodes, setEdges) {
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
}
