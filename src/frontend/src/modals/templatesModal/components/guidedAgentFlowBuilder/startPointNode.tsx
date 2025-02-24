import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Handle, Position } from '@xyflow/react';
import { Input, Textarea } from '@headlessui/react';
import BaseModal from '@/modals/baseModal';
import './startPointNode.css';
import ForwardedIconComponent from '@/components/common/genericIconComponent';

const styles = {
  nodeContainer: 'nodeContainer',
  contentContainer: 'contentContainer',
  header: 'header',
  inputContainer: 'inputContainer',
  input: 'input',
  icon: 'icon',
  textarea: 'textarea',
  addButton: 'addButton',
  nodeWrapper: 'nodeWrapper',
  handleButtom: 'handleButtom',
  deleteButton: 'deleteButton',
  deleteIcon: 'deleteIcon',
};  

const StartPointNode = ({ data, isConnectable }) => {
  const [showMenu, setShowMenu] = useState(false);
  const [menuPosition, setMenuPosition] = useState({ x: 0, y: 0 });
  const [currentnodeid, setcurrentnodeid] = useState("");
  const menuRef = useRef<HTMLDivElement>(null);
  const { label, onAddNode, onInputChange, instruction, onDeleteNode } = data;

  const handleAddNode = (nodeType) => {
    if (data.onAddNode) {
      console.log("handleAddNode", data.id)
      data.onAddNode(nodeType); // Pass node id and selected type
    }
    setShowMenu(false);
  };


  const handleAddNodeClick = useCallback(() => {
    setcurrentnodeid(data.id); // Save the node ID in the state
    console.log("setcurrentnodeid", currentnodeid);
    setShowMenu(true); // Show menu for this node
  }, [currentnodeid, setcurrentnodeid]);

  const handleInputChange = (e) => {
    const newValue = e.target.value;
    if (data.onInputChange) {
      data.onInputChange(newValue); // Pass updated value to callback
    }
  };

  useEffect(() => {
    const handleOutsideClick = (event) => {
      if (menuRef.current && !menuRef.current.contains(event.target)) {
        setShowMenu(false); // Hide the menu
      }
    };

    document.addEventListener("mousedown", handleOutsideClick);

    return () => {
      document.removeEventListener("mousedown", handleOutsideClick);
    };
  }, [setShowMenu]);

  return (
    <div className={styles.nodeWrapper}>
      <div className={styles.nodeContainer}>
        <div className={styles.contentContainer}>
  <header style={{
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'flex-start',
      fontSize: '16px',
      fontWeight: '600',
      color: '#1f2937',
      gap: '8px',
    }}>
      <ForwardedIconComponent name="flag" className={styles.icon} />
      <span>Starting Point</span>
  </header>
        </div>
        <Handle
          type="source"
          position={Position.Bottom}
          id="a"
          isConnectable={isConnectable}
          className={styles.handleButtom}
        />
      </div>
      <button className={styles.addButton} onClick={handleAddNodeClick}>
        +
      </button>
      {showMenu && (
        <div
          ref={menuRef}
          style={{
            position: 'absolute',
            top: '120px',
            backgroundColor: '#fff',
            border: '1px solid #e0e0e0',
            borderRadius: '8px',
            padding: '12px',
            boxShadow: '0 4px 8px rgba(0, 0, 0, 0.1)',
            zIndex: 1000,
            minWidth: '200px',
            fontFamily: 'Arial, sans-serif',
            width: 'max-content',
            display: 'grid',
          }}
        >
          {/* Add Instruction Node */}
          <div
            className={styles.contentContainer}
            style={{
              display: '-webkit-inline-box',
              alignItems: 'center',
              gap: '10px',
              marginBottom: '10px',
              padding: '8px',
              borderRadius: '6px',
              cursor: 'pointer',
              transition: 'background-color 0.2s ease-in-out',
              whiteSpace: 'nowrap', // Prevents text wrapping
              width: 'fit-content'
            }}
            onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = '#f9f9f9')}
            onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = '#fff')}
            onClick={() => handleAddNode('InstructionNode')}
          >
            <ForwardedIconComponent
              name="badge-check"
              className={styles.icon}
            />
            <span
              style={{
                color: '#333',
                fontSize: '14px',
                fontWeight: 'bold',
              }}
            >
              Instruction Node
            </span>
          </div>

          {/* Add Condition Node */}
          <div
            className={styles.contentContainer}
            style={{
              display: '-webkit-inline-box',
              alignItems: 'center',
              gap: '10px',
              padding: '8px',
              borderRadius: '6px',
              cursor: 'pointer',
              transition: 'background-color 0.2s ease-in-out',
              whiteSpace: 'nowrap', // Prevents text wrapping
              width: 'fit-content'
            }}
            onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = '#f9f9f9')}
            onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = '#fff')}
            onClick={() => handleAddNode('ConditionNode')}
          >
            <ForwardedIconComponent
              name="workflow"
              className={styles.icon}
            />
            <span
              style={{
                color: '#333',
                fontSize: '14px',
                fontWeight: 'bold',
              }}
            >
              Condition Node
            </span>
          </div>
        </div>
      )}
    </div>
  );
};

export default StartPointNode;
