import React from 'react';
import BaseModal from "@/modals/baseModal";
import { Input } from '@/components/ui/input'; // Adjust the path as necessary
import TextAreaComponent from '@/components/core/parameterRenderComponent/components/textAreaComponent'; // Adjust the path as necessary

export default function GuidedAgentAbilities() {
    return (
            <div className="flex flex-1 flex-col gap-4 md:gap-8">
                <BaseModal.Header description="Describe how your agent should work. It's recommended to provide examples of tasks it might receive and what to do.">
                    Core instructions
                </BaseModal.Header>
                <div className="flex flex-col gap-4">
                    <div className="flex flex-col gap-2">
                        <label htmlFor="agentPrompt" className="text-sm font-medium text-gray-700">
                            Agent Prompt
                        </label>
                        <TextAreaComponent
                            id="agentPrompt"
                            value={""}
                            handleOnNewValue={() => {}}
                            placeholder="Enter the prompt for the agent"
                            disabled={false}
                            editNode={false} // Added editNode prop
                        />
                    </div>
                </div>
            </div>
        );
}