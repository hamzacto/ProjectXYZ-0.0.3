import React from 'react';
import BaseModal from "@/modals/baseModal";
import { Input } from '@/components/ui/input'; // Adjust the path as necessary
import TextAreaComponent from '@/components/core/parameterRenderComponent/components/textAreaComponent'; // Adjust the path as necessary

export default function CreateAIAgentComponent({ name, setName, description, setDescription}) {
    return (
        <div className="flex flex-1 flex-col gap-4 md:gap-8">
            <BaseModal.Header description="Create a new AI Agent by providing the necessary details.">
                Create AI Agent
            </BaseModal.Header>
            <div className="flex flex-col gap-4">
                <div className="flex flex-col gap-2">
                    <label htmlFor="agentName" className="text-sm font-medium text-gray-700 dark:text-gray-200">
                        Agent Name
                    </label>
                    <Input
                        id="agentName"
                        value={name}
                        onChange={(e) => setName(e.target.value)}
                        placeholder="Enter the agent's name"
                    />
                </div>
                <div className="flex flex-col gap-2">
                    <label htmlFor="agentDescription" className="text-sm font-medium text-gray-700 dark:text-gray-200">
                        Agent Description
                    </label>
                    <TextAreaComponent
                        id="agentDescription"
                        value={description}
                        handleOnNewValue={(e) => setDescription(e.value)}
                        placeholder="Enter a description for the agent"
                        disabled={false}
                        editNode={false} // Added editNode prop
                    />
                </div>
            </div>
        </div>
    );
}