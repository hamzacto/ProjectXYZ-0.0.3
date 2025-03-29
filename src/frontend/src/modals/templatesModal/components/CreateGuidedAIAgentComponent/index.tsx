import React, { useState } from 'react';
import BaseModal from "@/modals/baseModal";
import { Input } from '@/components/ui/input'; // Adjust the path as necessary
import TextAreaComponent from '@/components/core/parameterRenderComponent/components/textAreaComponent'; // Adjust the path as necessary
import { IconRobot } from '@tabler/icons-react';
import { cn, getNumberFromString } from '@/utils/utils';

// Import avatar SVGs
import RobotAvatar from '@/assets/agent-avatars/robot.svg';
import AssistantAvatar from '@/assets/agent-avatars/assistant.svg';
import ScientistAvatar from '@/assets/agent-avatars/scientist.svg';
import ResearcherAvatar from '@/assets/agent-avatars/researcher.svg';
import TeacherAvatar from '@/assets/agent-avatars/teacher.svg';
import { ForwardIcon } from 'lucide-react';
import { Avatar1Icon } from '@/icons/AvatarIcon/AvatarIcon';
import Avatar2Icon from '@/icons/Avatar2Icon';
import { ForwardedIconComponent } from '@/components/common/genericIconComponent';
import { swatchColors } from '@/utils/styleUtils';
import AvatarResearcherIcon from '@/icons/AvatarResearcherIcon/AvatarResearcherIcon';
import AvatarBookAuthorIcon from '@/icons/AvatarBookAuthor/AvatarBookAuthor';
import AvatarDetectiveIcon from '@/icons/AvatarDetectiveIcon/AvatarDetectiveIcon';
import AvatarAstronautIcon from '@/icons/AvatarAstonaut/AvatarAstronautIcon';
import AvatarCyberpunckIcon from '@/icons/AvatarCyberpunck/AvatarCyberpunckIcon';
// import { ForwardedIconComponent } from '@/components/common/genericIconComponent';
const swatchIndex = 15;
// Define available avatar options
const AGENT_AVATARS = [
    // { id: 'Avatar', name: 'Avatar', icon: Avatar1Icon },
    { id: 'Avatar2', name: 'Avatar2', icon: Avatar2Icon },
    { id: 'AvatarResearcher', name: 'AvatarResearcher', icon: AvatarResearcherIcon },
    { id: 'AvatarBookAuthor', name: 'AvatarBookAuthor', icon: AvatarBookAuthorIcon },
    { id: 'AvatarDetective', name: 'AvatarDetective', icon: AvatarDetectiveIcon },
    { id: 'AvatarAstronaut', name: 'AvatarAstronaut', icon: AvatarAstronautIcon },
    { id: 'AvatarCyberpunck', name: 'AvatarCyberpunck', icon: AvatarCyberpunckIcon },
];

export default function CreateAIAgentComponent({ name, setName, description, setDescription, icon, setIcon }) {
    const [selectedAvatar, setSelectedAvatar] = useState(icon || AGENT_AVATARS[0].id);

    const handleAvatarSelect = (avatarId) => {
        setSelectedAvatar(avatarId);
        if (setIcon) {
            setIcon(avatarId);
        }
    };

    return (
        <div className="flex flex-1 flex-col gap-4 md:gap-8">
            <BaseModal.Header description="Create a new AI Agent by providing the necessary details.">
                <span className="flex items-center gap-2">
                    <IconRobot className="w-5 h-5" />
                    Create AI Agent
                </span>
            </BaseModal.Header>
            <div className="flex flex-col gap-4">
                <div className="flex flex-col gap-2">
                    <label className="text-sm font-medium text-gray-700 dark:text-gray-200">
                        Agent Avatar
                    </label>
                    <div className="flex flex-wrap gap-4">
                        {AGENT_AVATARS.map((avatar) => {
                            return (
                                <button
                                    key={avatar.id}
                                    type="button"
                                    className={cn(
                                        "flex flex-col items-center justify-center rounded-lg border-2 transition-all",
                                        selectedAvatar === avatar.id
                                            ? "border-blue-500 bg-blue-50 dark:bg-blue-900/20"
                                            : "border-gray-200 hover:border-gray-300 dark:border-gray-700 dark:hover:border-gray-600"
                                    )}
                                    onClick={() => handleAvatarSelect(avatar.id)}
                                >
                                    {/* Icon */}
                                    <div
                                        className={cn(
                                            `grid place-items-center h-20 w-20 rounded-lg p-0 bg-transparent`,
                                            swatchColors[swatchIndex],
                                        )}
                                    >
                                        <ForwardedIconComponent
                                            name={avatar.name}
                                            aria-hidden="true"
                                            className="h-16 w-16"
                                        />
                                    </div>
                                </button>
                            );
                        })}
                    </div>
                </div>
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
                        editNode={false}
                    />
                </div>
            </div>
        </div>
    );
}