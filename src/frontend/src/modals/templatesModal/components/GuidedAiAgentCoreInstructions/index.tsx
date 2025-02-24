import React, { useState } from 'react';
import BaseModal from "@/modals/baseModal";
import { HelpCircle, Copy, Lightbulb, CheckCircle2, PenLine, Info, ArrowRight, ArrowLeft } from 'lucide-react';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import ForwardedIconComponent from '@/components/common/genericIconComponent';
import { Button } from '@/components/ui/button';
import PromptTextAreaComponent from '@/components/core/parameterRenderComponent/components/promptTextAreaComponent';
import { Card, CardHeader, CardContent } from "@/components/ui/card";
import { motion, AnimatePresence } from "framer-motion";
import { IconBrain} from '@tabler/icons-react';
const ProTipsCard = () => (
    <Card className="bg-blue-50/80 border-blue-100 dark:bg-blue-950/10 dark:border-blue-900/20">
        <CardHeader className="pb-2">
            <div className="flex items-center gap-2 text-blue-900 dark:text-blue-200">
                <Lightbulb className="h-4 w-4 text-blue-500 dark:text-blue-400" />
                <span className="font-medium">Pro Tips</span>
            </div>
        </CardHeader>
        <CardContent>
            <ul className="space-y-1.5 text-sm text-blue-900 dark:text-blue-200">
                <li className="flex gap-2">
                    <span className="font-medium">•</span>
                    <span><strong>Define the role</strong> - Set clear expertise and capabilities</span>
                </li>
                <li className="flex gap-2">
                    <span className="font-medium">•</span>
                    <span><strong>Show examples</strong> - Include sample tasks and responses</span>
                </li>
                <li className="flex gap-2">
                    <span className="font-medium">•</span>
                    <span><strong>Set boundaries</strong> - Specify what the agent should/shouldn't do</span>
                </li>
            </ul>
        </CardContent>
    </Card>
);

const WritingGuidelinesCard = () => (
    <Card className="bg-amber-50/80 border-amber-100 dark:bg-amber-950/10 dark:border-amber-900/20">
        <CardHeader className="pb-2">
            <div className="flex items-center gap-2 text-amber-900 dark:text-amber-200">
                <Info className="h-4 w-4 text-amber-500 dark:text-amber-400" />
                <span className="font-medium">Writing Guidelines</span>
            </div>
        </CardHeader>
        <CardContent>
            <ul className="space-y-1.5 text-sm text-amber-900 dark:text-amber-200">
                <li className="flex gap-2">
                    <span className="font-medium">•</span>
                    Use clear, specific language
                </li>
                <li className="flex gap-2">
                    <span className="font-medium">•</span>
                    Structure instructions in logical sections
                </li>
                <li className="flex gap-2">
                    <span className="font-medium">•</span>
                    Include response format preferences
                </li>
            </ul>
        </CardContent>
    </Card>
);

export default function GuidedAiAgentCoreInstructions({ prompt, setPrompt }) {
    const [copySuccess, setCopySuccess] = useState(false);
    const [isFlipped, setIsFlipped] = useState(false);

    const examplePrompt = `You are a research analyst specialized in market analysis. Your tasks include:...`;


    const handleCopyExample = async () => {
        await navigator.clipboard.writeText(examplePrompt);
        setCopySuccess(true);
        setTimeout(() => setCopySuccess(false), 2000);
    };

    return (
        <div className="flex flex-1 flex-col gap-4 md:gap-8">
            <BaseModal.Header
                description="Describe how your agent should work. It's recommended to provide examples of tasks it might receive and what to do."
            >
                <span className="flex items-center gap-2">
                    <IconBrain className="w-5 h-5" />
                    Core instructions
                </span>
            </BaseModal.Header>

            <div className="flex flex-col">
                <div className="flex flex-col gap-2">
                    <label
                        htmlFor="agentPrompt"
                        className="text-sm font-medium text-gray-700 dark:text-gray-200"
                        aria-label="Enter your agent's core instructions"
                    >
                        Agent Prompt
                    </label>
                    {/* <TooltipProvider delayDuration={300}>
                                <Tooltip>
                                    <TooltipTrigger asChild>
                                        <HelpCircle className="h-4 w-4 text-gray-400 dark:text-gray-500 cursor-help" />
                                    </TooltipTrigger>
                                    <TooltipContent
                                        className="max-w-sm p-3"
                                        sideOffset={5}
                                    >
                                        <p>Define how your agent should behave and what tasks it can handle. Include specific examples for better results.</p>
                                    </TooltipContent>
                                </Tooltip>
                            </TooltipProvider> */}
                    {/* <Button
                            variant="ghost"
                            size="sm"
                            onClick={handleCopyExample}
                            className="h-8 gap-2 text-xs font-medium text-gray-600 hover:text-gray-900 dark:text-gray-400 dark:hover:text-gray-200 hover:bg-gray-100/80 dark:hover:bg-gray-800/80 transition-colors"
                            aria-label="Copy example prompt"
                        >
                            {copySuccess ? (
                                <CheckCircle2 className="h-3.5 w-3.5 text-green-500 dark:text-green-400" />
                            ) : (
                                <Copy className="h-3.5 w-3.5" />
                            )}
                            {copySuccess ? 'Copied!' : 'Copy example'}
                        </Button> */}
                    <PromptTextAreaComponent
                        id="agentPrompt"
                        value={prompt}
                        handleOnNewValue={(e) => setPrompt(e.value)}
                        placeholder={examplePrompt}
                        disabled={false}
                        editNode={false}
                    />


                    <div className="relative w-full">
                        <Button
                            variant="ghost"
                            size="sm"
                            className="absolute right-4 top-4 z-10"
                            onClick={() => setIsFlipped(!isFlipped)}
                        >
                            {isFlipped ? (
                                <ArrowLeft className="h-4 w-4" />
                            ) : (
                                <ArrowRight className="h-4 w-4" />
                            )}
                        </Button>

                        <AnimatePresence initial={false} mode="wait">
                            {!isFlipped ? (
                                <motion.div
                                    key="proTips"
                                    initial={{ opacity: 0, x: -20 }}
                                    animate={{ opacity: 1, x: 0 }}
                                    exit={{ opacity: 0, x: 20 }}
                                    transition={{ duration: 0.3 }}
                                    className="absolute inset-0"
                                >
                                    <ProTipsCard />
                                </motion.div>
                            ) : (
                                <motion.div
                                    key="guidelines"
                                    initial={{ opacity: 0, x: -20 }}
                                    animate={{ opacity: 1, x: 0 }}
                                    exit={{ opacity: 0, x: 20 }}
                                    transition={{ duration: 0.3 }}
                                    className="absolute inset-0"
                                >
                                    <WritingGuidelinesCard />
                                </motion.div>
                            )}
                        </AnimatePresence>
                    </div>
                </div>
            </div>
        </div>
    );
}