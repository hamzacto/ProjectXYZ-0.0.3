import React, { useState } from 'react';
import { Button } from "@/components/ui/button";
import BaseModal from '@/modals/baseModal'; 

interface GuidedAgentFormProps {
  open: boolean;
  setOpen: (open: boolean) => void;
}

const GuidedAgentForm: React.FC<GuidedAgentFormProps> = ({ open, setOpen }) => {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [prompt, setPrompt] = useState("");

  const handleSubmit = () => {
    // Handle form submission
    console.log("Form submitted", { name, description, prompt });
    // Close the modal after submission
    setOpen(false);
  };

  return (
    <BaseModal open={open} setOpen={setOpen}>
      <BaseModal.Content>
        <div className="flex flex-col gap-4 p-4">
          <h2 className="text-lg font-semibold">Create Guided Agent</h2>
          <div>
            <label className="block text-sm font-medium">Agent Name</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="mt-1 block w-full rounded-md border-gray-300 shadow-sm"
            />
          </div>
          <div>
            <label className="block text-sm font-medium">Description</label>
            <input
              type="text"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="mt-1 block w-full rounded-md border-gray-300 shadow-sm"
            />
          </div>
          <div>
            <label className="block text-sm font-medium">Prompt</label>
            <textarea
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              className="mt-1 block w-full rounded-md border-gray-300 shadow-sm"
            />
          </div>
          <div className="flex justify-end gap-2">
            <Button onClick={() => setOpen(false)}>Cancel</Button>
            <Button onClick={handleSubmit}>Create</Button>
          </div>
        </div>
      </BaseModal.Content>
    </BaseModal>
  );
};

export default GuidedAgentForm;