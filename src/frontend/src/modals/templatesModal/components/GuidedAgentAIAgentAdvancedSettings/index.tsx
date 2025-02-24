import React from 'react';
import BaseModal from "@/modals/baseModal";
import { Input } from '@/components/ui/input';
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import { motion } from "framer-motion";
import { 
    IconAdjustments, 
    IconBolt, 
    IconClock, 
    IconRefresh,
    IconBulb,
    IconTarget,
    IconScale,
    IconBrackets,
    IconPlant2,
    IconMaximize,
    IconBug,
    IconThermometer,
    IconGauge
} from "@tabler/icons-react";
import { Switch } from "@/components/ui/switch";
import IntComponent from "@/components/core/parameterRenderComponent/components/intComponent";
import FloatComponent from "@/components/core/parameterRenderComponent/components/floatComponent";
import { APIClassType } from "@/types/api";
import { FaTemperatureHalf } from "react-icons/fa6";
import { VscJson } from "react-icons/vsc";

interface AdvancedSettingsProps {
    settings: {
        temperature: number;
        modelName: string;
        maxRetries: number;
        timeout: number;
        seed: number;
        jsonMode: boolean;
        maxTokens: number;
        handleParseErrors: boolean;
    };
    onSettingsChange: (settings: {
        temperature: number;
        modelName: string;
        maxRetries: number;
        timeout: number;
        seed: number;
        jsonMode: boolean;
        maxTokens: number;
        handleParseErrors: boolean;
    }) => void;
}

const OPENAI_MODELS = [
    "gpt-4o-mini",
    "gpt-4o",
    "gpt-3.5-turbo",
    "gpt-4-turbo",
    "gpt-4-turbo-preview",
    "gpt-4",
    "gpt-3.5-turbo-0125"

];

const TemperatureModeInfo = {
    precise: {
        icon: <IconTarget className="w-4 h-4" />,
        label: 'More Precise',
        color: 'from-blue-500 to-blue-600'
    },
    balanced: {
        icon: <IconScale className="w-4 h-4" />,
        label: 'Balanced',
        color: 'from-violet-500 to-violet-600'
    },
    creative: {
        icon: <IconBulb className="w-4 h-4" />,
        label: 'More Creative',
        color: 'from-orange-500 to-orange-600'
    }
};

const getTemperatureMode = (temp: number) => {
    if (temp < 0.3) return 'precise';
    if (temp < 0.7) return 'balanced';
    return 'creative';
};

const defaultNodeClass: APIClassType = {
    description: "Input Component",
    template: {},
    display_name: "Input Component",
    documentation: "A component for input values",
};

const SettingCard = ({ children, icon, title, description }: { 
    children: React.ReactNode; 
    icon: React.ReactNode;
    title: string;
    description?: string;
}) => (
    <motion.div 
        className="rounded-xl bg-white dark:bg-[#27272a] p-6 shadow-sm border border-gray-100 dark:border-gray-700
                   transition-all duration-200 hover:shadow-md"
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3 }}
    >
        <div className="flex items-start gap-4">
            <div className="rounded-lg bg-primary/10 p-2 text-primary">
                {icon}
            </div>
            <div className="flex-1 space-y-1">
                <h3 className="text-sm font-medium text-gray-900 dark:text-gray-100">
                    {title}
                </h3>
                {description && (
                    <p className="text-xs text-gray-500 dark:text-gray-400">
                        {description}
                    </p>
                )}
                <div className="pt-3">
                    {children}
                </div>
            </div>
        </div>
    </motion.div>
);

export default function GuidedAgentAIAgentAdvancedSettings({ settings, onSettingsChange }: AdvancedSettingsProps) {
    const handleSettingChange = (key: string, value: number | string | boolean) => {
        onSettingsChange({
            ...settings,
            [key]: value
        });
    };

    const currentMode = getTemperatureMode(settings.temperature);
    const modeInfo = TemperatureModeInfo[currentMode];

    return (
        <div className="flex flex-1 flex-col h-[calc(100vh-200px)] overflow-hidden">
            {/* Fixed Header */}
            <div className="flex-none pb-6 border-b border-gray-100 dark:border-gray-800 z-10">
                <BaseModal.Header description="Configure advanced settings for your AI agent's behavior and performance.">
                    <span className="flex items-center gap-2">
                        <IconAdjustments className="w-5 h-5" />
                        Advanced Settings
                    </span>
                </BaseModal.Header>
            </div>

            {/* Scrollable Content */}
            <div className="flex-1 overflow-y-auto px-2 py-6 
                scrollbar-thin scrollbar-thumb-gray-300 dark:scrollbar-thumb-gray-600 
                scrollbar-track-transparent hover:scrollbar-thumb-gray-400 
                dark:hover:scrollbar-thumb-gray-500">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 px-4">
                    {/* Temperature Setting */}
                    <SettingCard 
                        icon={<FaTemperatureHalf className="w-5 h-5" />}
                        title="Temperature"
                        description="Controls randomness in the model's responses"
                    >
                        <div className="space-y-6">
                            <div className="flex items-start justify-between">
                                <motion.div 
                                    className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-gray-100 dark:bg-gray-700"
                                    key={currentMode}
                                    initial={{ opacity: 0, x: -10 }}
                                    animate={{ opacity: 1, x: 0 }}
                                    transition={{ duration: 0.2 }}
                                >
                                    {modeInfo.icon}
                                    <span className="text-sm text-gray-700 dark:text-gray-200">
                                        {modeInfo.label}
                                    </span>
                                </motion.div>
                                <div className="relative flex items-center w-24">
                                    <FloatComponent
                                        value={settings.temperature}
                                        handleOnNewValue={({ value }) => handleSettingChange('temperature', value)}
                                        disabled={false}
                                        rangeSpec={{ min: 0, max: 1, step: 0.01 }}
                                        editNode={false}
                                        id="temperature-input"
                                        nodeClass={defaultNodeClass}
                                    />
                                </div>
                            </div>

                            <div className="space-y-4">
                                <Slider
                                    value={[settings.temperature]}
                                    onValueChange={(value) => handleSettingChange("temperature", value[0])}
                                    min={0}
                                    max={1}
                                    step={0.01}
                                    className="w-full [&_.slider-track]:h-1 [&_.slider-track]:bg-gradient-to-r [&_.slider-track]:from-blue-500 [&_.slider-track]:via-violet-500 [&_.slider-track]:to-orange-500 [&_.slider-track]:rounded-full [&_.slider-thumb]:w-4 [&_.slider-thumb]:h-4 [&_.slider-thumb]:bg-white [&_.slider-thumb]:border [&_.slider-thumb]:border-gray-200 [&_.slider-thumb]:shadow-sm hover:[&_.slider-thumb]:shadow-md"
                                />
                                <div className="flex justify-between px-2">
                                    <div className="flex items-center gap-1 text-xs text-gray-500">
                                        <IconTarget className="w-3 h-3" />
                                        Precise
                                    </div>
                                    <div className="flex items-center gap-1 text-xs text-gray-500">
                                        <IconScale className="w-3 h-3" />
                                        Balanced
                                    </div>
                                    <div className="flex items-center gap-1 text-xs text-gray-500">
                                        <IconBulb className="w-3 h-3" />
                                        Creative
                                    </div>
                                </div>
                            </div>
                        </div>
                    </SettingCard>

                    {/* Model Selection */}
                    <SettingCard 
                        icon={<IconAdjustments className="w-5 h-5" />}
                        title="Model"
                        description="Select the AI model for your agent"
                    >
                        <Select
                            value={settings.modelName}
                            onValueChange={(value) => handleSettingChange('modelName', value)}
                        >
                            <SelectTrigger className="w-full">
                                <SelectValue placeholder="Select a model" />
                            </SelectTrigger>
                            <SelectContent>
                                {OPENAI_MODELS.map((model) => (
                                    <SelectItem 
                                        key={model} 
                                        value={model}
                                        className="cursor-pointer transition-colors hover:bg-gray-100 dark:hover:bg-gray-700"
                                    >
                                        {model}
                                    </SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                    </SettingCard>

                    {/* Seed Setting */}
                    <SettingCard 
                        icon={<IconPlant2 className="w-5 h-5" />}
                        title="Seed"
                        description="Controls the reproducibility of the model's responses"
                    >
                        <IntComponent
                            value={settings.seed}
                            handleOnNewValue={({ value }) => handleSettingChange('seed', value)}
                            disabled={false}
                            rangeSpec={{ min: 0, max: Number.MAX_SAFE_INTEGER, step: 1 }}
                            editNode={false}
                            id="seed-input"
                            nodeClass={defaultNodeClass}
                        />
                    </SettingCard>

                    {/* JSON Mode Setting */}
                    <SettingCard 
                        icon={<VscJson className="w-5 h-5" />}
                        title="JSON Mode"
                        description="Force JSON output regardless of schema"
                    >
                        <div className="flex items-center justify-between">
                            <span className="text-sm text-gray-700 dark:text-gray-200">
                                Enable JSON Mode
                            </span>
                            <Switch
                                checked={settings.jsonMode}
                                onCheckedChange={(checked) => handleSettingChange('jsonMode', checked)}
                            />
                        </div>
                    </SettingCard>

                    {/* Max Tokens Setting */}
                    <SettingCard 
                        icon={<IconMaximize className="w-5 h-5" />}
                        title="Max Tokens"
                        description="Maximum number of tokens to generate (0 for unlimited)"
                    >
                        <IntComponent
                            value={settings.maxTokens}
                            handleOnNewValue={({ value }) => handleSettingChange('maxTokens', value)}
                            disabled={false}
                            rangeSpec={{ min: 0, max: Number.MAX_SAFE_INTEGER, step: 1 }}
                            editNode={false}
                            id="max-tokens-input"
                            nodeClass={defaultNodeClass}
                        />
                    </SettingCard>

                    {/* Handle Parse Errors Setting */}
                    <SettingCard 
                        icon={<IconBug className="w-5 h-5" />}
                        title="Handle Parse Errors"
                        description="Automatically fix errors when processing user input"
                    >
                        <div className="flex items-center justify-between">
                            <span className="text-sm text-gray-700 dark:text-gray-200">
                                Enable Error Handling
                            </span>
                            <Switch
                                checked={settings.handleParseErrors}
                                onCheckedChange={(checked) => handleSettingChange('handleParseErrors', checked)}
                            />
                        </div>
                    </SettingCard>

                    {/* Max Retries */}
                    <SettingCard 
                        icon={<IconRefresh className="w-5 h-5" />}
                        title="Max Retries"
                        description="Maximum number of retry attempts for failed requests"
                    >
                        <IntComponent
                            value={settings.maxRetries}
                            handleOnNewValue={({ value }) => handleSettingChange('maxRetries', value)}
                            disabled={false}
                            rangeSpec={{ min: 1, max: 10, step: 1 }}
                            editNode={false}
                            id="max-retries-input"
                            nodeClass={defaultNodeClass}
                        />
                    </SettingCard>

                    {/* Timeout */}
                    <SettingCard 
                        icon={<IconClock className="w-5 h-5" />}
                        title="Timeout"
                        description="Maximum time to wait for a response (in seconds)"
                    >
                        <IntComponent
                            value={settings.timeout}
                            handleOnNewValue={({ value }) => handleSettingChange('timeout', value)}
                            disabled={false}
                            rangeSpec={{ min: 30, max: 3600, step: 1 }}
                            editNode={false}
                            id="timeout-input"
                            nodeClass={defaultNodeClass}
                        />
                    </SettingCard>
                </div>
            </div>
        </div>
    );
}   
