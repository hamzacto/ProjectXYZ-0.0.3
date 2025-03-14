import { useState, useEffect } from 'react';
import { Button } from '@/components/ui/button';
import { useIntegrationStore } from '../GuidedAgentIntegrations/useIntegrationStore';
import { Badge } from '@/components/ui/badge';
import axios from 'axios';
import { AlertCircle, CheckCircle2, Mail, Play, Plus, Trash2, XCircle, Loader2, Bell, BellOff } from 'lucide-react';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Card, CardHeader, CardContent, CardDescription } from '@/components/ui/card';
import { useDarkStore } from '@/stores/darkStore';
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
    DialogDescription,
} from "@/components/ui/dialog";
import {
    Tooltip,
    TooltipContent,
    TooltipProvider,
    TooltipTrigger,
} from "@/components/ui/tooltip";
import { motion, AnimatePresence } from 'framer-motion';
import ForwardedIconComponent from '@/components/common/genericIconComponent';
import BaseModal from '@/modals/baseModal';
import { IconAdjustments, IconBell } from '@tabler/icons-react';

interface IntegrationDetails {
    id: string;
    service_name: string;
    connected: boolean;
    created_at: string;
    updated_at: string;
    expires_at: string | null;
    permissions: string[];
    email: string | null;
    status: 'active' | 'expired' | 'error';
    integration_metadata?: {
        user_display_name?: string;
        team_name?: string;
        [key: string]: any;
    };
}

interface GuidedAgentTriggersProps {
    onTriggersChange?: (triggers: string[]) => void;
    selectedTriggers: string[];
    setSelectedTriggers: React.Dispatch<React.SetStateAction<string[]>>;
}

const cardVariants = {
    hidden: { opacity: 0, y: 20 },
    visible: { opacity: 1, y: 0 }
};

const listItemVariants = {
    hidden: { opacity: 0 },
    visible: { opacity: 1 }
};

export default function GuidedAgentTriggers({ onTriggersChange, selectedTriggers, setSelectedTriggers }: GuidedAgentTriggersProps) {
    const [integrations, setIntegrations] = useState<IntegrationDetails[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [successMessage, setSuccessMessage] = useState<string | null>(null);
    const [dialogOpen, setDialogOpen] = useState(false);
    const [slackDialogOpen, setSlackDialogOpen] = useState(false);
    const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
    const [triggerToDelete, setTriggerToDelete] = useState<string | null>(null);
    const axiosInstance = axios.create({
        baseURL: '/api/v1',
        headers: useIntegrationStore.getState().getAuthHeaders(),
        withCredentials: true
    });
    const dark = useDarkStore((state) => state.dark);

    const fetchIntegrations = async () => {
        setLoading(true);
        setError(null);
        try {
            const response = await axiosInstance.get('/integration/status');
            setIntegrations(response.data.integrations);
        } catch (err) {
            setError('Failed to fetch integrations');
            console.error(err);
        } finally {
            setLoading(false);
        }
    };

    const createTrigger = async (integrationId: string, serviceName: string) => {
        try {
            // Format the trigger as "service_name:integration_id"
            const triggerValue = `${serviceName}:${integrationId}`;
            setSelectedTriggers(prev => [...prev, triggerValue]);
            setSuccessMessage('Trigger set successfully');
            onTriggersChange?.([...selectedTriggers, triggerValue]);
            setTimeout(() => setSuccessMessage(null), 3000);
        } catch (err) {
            setError('Failed to create trigger');
            console.error(err);
        }
    };

    const handleDeleteTrigger = (triggerId: string) => {
        setSelectedTriggers(prev => prev.filter(id => id !== triggerId));
        onTriggersChange?.(selectedTriggers.filter(id => id !== triggerId));
        setDeleteDialogOpen(false);
        setTriggerToDelete(null);
    };

    useEffect(() => {
        fetchIntegrations();
    }, []);

    const getActiveIntegrations = () => {
        return integrations.filter(integration =>
            selectedTriggers.some(trigger => trigger === `${integration.service_name}:${integration.id}`)
        );
    };

    const getInactiveIntegrations = () => {
        return integrations.filter(integration =>
            !selectedTriggers.some(trigger => trigger === `${integration.service_name}:${integration.id}`)
        );
    };

    const getInactiveIntegrationsByService = (serviceName: string) => {
        return integrations.filter(integration =>
            !selectedTriggers.some(trigger => trigger === `${integration.service_name}:${integration.id}`) &&
            integration.service_name.toLowerCase() === serviceName.toLowerCase()
        );
    };

    const getServiceIcon = (serviceName: string) => {
        const serviceIcons = {
            'gmail': 'Gmail',
            'slack': 'Slack',
            'whatsapp': 'WhatsApp'
        };
        
        return serviceIcons[serviceName.toLowerCase()] || 'Mail';
    };

    const getStatusIcon = (status: string) => {
        const icons = {
            active: {
                icon: <CheckCircle2 className="h-4 w-4 text-green-500" />,
                tooltip: "Integration is active and working"
            },
            expired: {
                icon: <AlertCircle className="h-4 w-4 text-yellow-500" />,
                tooltip: "Integration has expired"
            },
            error: {
                icon: <XCircle className="h-4 w-4 text-red-500" />,
                tooltip: "Error with integration"
            }
        };

        const statusData = icons[status as keyof typeof icons];
        if (!statusData) return null;

        return (
            <TooltipProvider>
                <Tooltip>
                    <TooltipTrigger>{statusData.icon}</TooltipTrigger>
                    <TooltipContent>
                        <p>{statusData.tooltip}</p>
                    </TooltipContent>
                </Tooltip>
            </TooltipProvider>
        );
    };

    return (
        <div className="flex flex-1 flex-col overflow-hidden">
            <div className="flex-none border-b border-gray-100 dark:border-gray-800 pb-4">
                <BaseModal.Header description="Enable task creation for your agent from external sources like emails or WhatsApp, allowing seamless threading into the same task.">
                    <span className="flex items-center gap-2">
                        <IconBell className="w-5 h-5" />
                        Configure Triggers
                    </span>
                </BaseModal.Header>
            </div>

            <div className="flex-1 overflow-y-auto py-4">
                <div className="space-y-8">
                    <motion.div
                        initial={{ opacity: 0, y: 10 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ duration: 0.2 }}
                    >
                        <div className="space-y-2">
                            <div className="space-y-1">
                                <h2 className="text-l font-semibold text-gray-900 dark:text-gray-100">Active Triggers</h2>
                                <p className="text-sm text-gray-500 dark:text-gray-400">
                                    Currently active integrations that will create tasks for this agent
                                </p>
                            </div>
                            
                            <div className="pt-4 space-y-2">
                                {loading ? (
                                    <div className="flex items-center justify-center py-8">
                                        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                                    </div>
                                ) : getActiveIntegrations().length > 0 ? (
                                    <div className="space-y-2">
                                        {getActiveIntegrations().map(integration => (
                                            <motion.div
                                                key={integration.id}
                                                initial={{ opacity: 0 }}
                                                animate={{ opacity: 1 }}
                                                transition={{ duration: 0.2 }}
                                            >
                                                <div className="flex items-center justify-between p-4 rounded-lg bg-white dark:bg-[#27272a] border border-gray-100 dark:border-gray-700">
                                                    <div className="flex items-center gap-2">
                                                        <ForwardedIconComponent name={getServiceIcon(integration.service_name)} className="h-5 w-5 text-gray-600 dark:text-gray-400" />
                                                        {getStatusIcon(integration.status)}
                                                        <span className="text-sm dark:text-gray-300">
                                                            {integration.email || 
                                                             (integration.integration_metadata?.user_display_name ? 
                                                              `${integration.integration_metadata.user_display_name}` : 
                                                              integration.service_name)}
                                                        </span>
                                                    </div>
                                                    <TooltipProvider>
                                                        <Tooltip>
                                                            <TooltipTrigger asChild>
                                                                <Button
                                                                    variant="ghost"
                                                                    size="sm"
                                                                    onClick={() => handleDeleteTrigger(`${integration.service_name}:${integration.id}`)}
                                                                    className="hover:text-destructive transition-colors duration-200"
                                                                >
                                                                    <Trash2 className="h-4 w-4" />
                                                                </Button>
                                                            </TooltipTrigger>
                                                            <TooltipContent>
                                                                <p>Remove trigger</p>
                                                            </TooltipContent>
                                                        </Tooltip>
                                                    </TooltipProvider>
                                                </div>
                                            </motion.div>
                                        ))}
                                    </div>
                                ) : (
                                    <div className="flex items-center justify-center p-8 rounded-lg border border-dashed border-gray-200 dark:border-gray-700 dark:bg-[#27272a]">
                                        <div className="text-center space-y-2">
                                            <BellOff className="mx-auto h-8 w-8 text-gray-400 dark:text-gray-600" />
                                            <p className="text-sm text-gray-500 dark:text-gray-400">No active triggers</p>
                                        </div>
                                    </div>
                                )}
                            </div>
                        </div>
                    </motion.div>

                    <motion.div
                        initial={{ opacity: 0, y: 10 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ duration: 0.2 }}
                    >
                        <div className="space-y-4">
                            <div className="space-y-1">
                                <h2 className="text-l font-semibold text-gray-900 dark:text-gray-100">Available Triggers</h2>
                            </div>
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-2">
                                <div className="group rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-[#27272a] p-6 transition-all duration-200 hover:shadow-sm">
                                    <div className="flex items-start justify-between mb-4">
                                        <div>
                                            <h3 className="text-base font-semibold dark:text-gray-100">Gmail</h3>
                                            <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                                                Connect Gmail accounts to create automated workflows
                                            </p>
                                        </div>
                                        <ForwardedIconComponent name="Gmail" className="h-6 w-6 text-gray-600 dark:text-gray-400" />
                                    </div>
                                    <Button
                                        variant="outline"
                                        className="w-full justify-start gap-2"
                                        onClick={() => setDialogOpen(true)}
                                    >
                                        <Plus className="h-4 w-4" />
                                        Add Gmail Trigger
                                    </Button>
                                </div>

                                <div className="group rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-[#27272a] p-6 transition-all duration-200 hover:shadow-sm">
                                    <div className="flex items-start justify-between mb-4">
                                        <div>
                                            <h3 className="text-base font-semibold dark:text-gray-100">Slack</h3>
                                            <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                                                Connect Slack workspaces to create automated workflows
                                            </p>
                                        </div>
                                        <ForwardedIconComponent name="Slack" className="h-6 w-6 text-gray-600 dark:text-gray-400" />
                                    </div>
                                    <Button
                                        variant="outline"
                                        className="w-full justify-start gap-2"
                                        onClick={() => setSlackDialogOpen(true)}
                                    >
                                        <Plus className="h-4 w-4" />
                                        Add Slack Trigger
                                    </Button>
                                </div>

                                <div className="group rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-[#27272a] p-6 transition-all duration-200 hover:shadow-sm">
                                    <div className="flex items-start justify-between mb-4">
                                        <div>
                                            <h3 className="text-base font-semibold dark:text-gray-100">WhatsApp</h3>
                                            <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                                                Connect WhatsApp accounts to create automated workflows
                                            </p>
                                        </div>
                                        <ForwardedIconComponent name="WhatsApp" className="h-6 w-6 text-gray-600 dark:text-gray-400" />
                                    </div>
                                    <Button
                                        variant="outline"
                                        className="w-full justify-start gap-2"
                                    >
                                        <Plus className="h-4 w-4" />
                                        Add WhatsApp Trigger
                                    </Button>
                                </div>
                            </div>
                        </div>
                    </motion.div>
                </div>
            </div>

            <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
                <DialogContent className="max-w-xl dark:bg-[#27272a] dark:border-gray-700">
                    <DialogHeader>
                        <DialogTitle className="dark:text-gray-100">Select Gmail Account</DialogTitle>
                        <DialogDescription className="dark:text-gray-400">
                            Choose an account to create a new trigger
                        </DialogDescription>
                    </DialogHeader>

                    <div className="max-h-[60vh] overflow-y-auto">
                        <div className="space-y-4 pr-4">
                            {getInactiveIntegrationsByService('gmail').length === 0 ? (
                                <Card className="flex items-center justify-center p-4 text-center dark:bg-[#27272a] dark:border-gray-600">
                                    <div className="space-y-3">
                                        <Mail className="mx-auto h-12 w-12 text-muted-foreground opacity-50" />
                                        <p className="text-muted-foreground dark:text-gray-400">No available Gmail accounts</p>
                                    </div>
                                </Card>
                            ) : (
                                getInactiveIntegrationsByService('gmail').map((integration) => (
                                    <Card key={integration.id} className="p-4 dark:bg-[#27272a] dark:border-gray-600">
                                        <div className="flex items-start justify-between">
                                            <div className="space-y-3">
                                                <div className="flex items-center gap-2">
                                                    <span className="font-medium dark:text-gray-200">{integration.email}</span>
                                                </div>
                                                <div className="flex flex-wrap gap-2">
                                                    {integration.permissions.map((permission) => (
                                                        <Badge
                                                            key={permission}
                                                            variant="secondary"
                                                            className="text-xs dark:bg-gray-600 dark:text-gray-300"
                                                        >
                                                            {permission}
                                                        </Badge>
                                                    ))}
                                                </div>
                                            </div>
                                            <Button
                                                variant="outline"
                                                size="sm"
                                                onClick={() => {
                                                    createTrigger(integration.id, integration.service_name);
                                                    setDialogOpen(false);
                                                }}
                                                className="dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-600"
                                            >
                                                Select Account
                                            </Button>
                                        </div>
                                    </Card>
                                ))
                            )}
                        </div>
                    </div>
                </DialogContent>
            </Dialog>

            <Dialog open={slackDialogOpen} onOpenChange={setSlackDialogOpen}>
                <DialogContent className="max-w-xl dark:bg-[#27272a] dark:border-gray-700">
                    <DialogHeader>
                        <DialogTitle className="dark:text-gray-100">Select Slack Workspace</DialogTitle>
                        <DialogDescription className="dark:text-gray-400">
                            Choose a workspace to create a new trigger
                        </DialogDescription>
                    </DialogHeader>

                    <div className="max-h-[60vh] overflow-y-auto">
                        <div className="space-y-4 pr-4">
                            {getInactiveIntegrationsByService('slack').length === 0 ? (
                                <Card className="flex items-center justify-center p-4 text-center dark:bg-[#27272a] dark:border-gray-600">
                                    <div className="space-y-3">
                                        <Mail className="mx-auto h-12 w-12 text-muted-foreground opacity-50" />
                                        <p className="text-muted-foreground dark:text-gray-400">No available Slack workspaces</p>
                                    </div>
                                </Card>
                            ) : (
                                getInactiveIntegrationsByService('slack').map((integration) => (
                                    <Card key={integration.id} className="p-4 dark:bg-[#27272a] dark:border-gray-600">
                                        <div className="flex items-start justify-between">
                                            <div className="space-y-3">
                                                <div className="flex items-center gap-2">
                                                    <span className="font-medium dark:text-gray-200">
                                                        {integration.email || 
                                                         (integration.integration_metadata?.user_display_name ? 
                                                          `${integration.integration_metadata.user_display_name}` : 
                                                          integration.service_name)}
                                                    </span>
                                                </div>
                                                <div className="flex flex-wrap gap-2">
                                                    {integration.permissions.map((permission) => (
                                                        <Badge
                                                            key={permission}
                                                            variant="secondary"
                                                            className="text-xs dark:bg-gray-600 dark:text-gray-300"
                                                        >
                                                            {permission}
                                                        </Badge>
                                                    ))}
                                                </div>
                                            </div>
                                            <Button
                                                variant="outline"
                                                size="sm"
                                                onClick={() => {
                                                    createTrigger(integration.id, integration.service_name);
                                                    setSlackDialogOpen(false);
                                                }}
                                                className="dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-600"
                                            >
                                                Select Workspace
                                            </Button>
                                        </div>
                                    </Card>
                                ))
                            )}
                        </div>
                    </div>
                </DialogContent>
            </Dialog>

            <Dialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
                <DialogContent className="dark:bg-[#27272a] dark:border-gray-700">
                    <DialogHeader>
                        <DialogTitle className="dark:text-gray-100">
                            <div className="flex items-center">
                                <span className="pr-2">Delete Trigger</span>
                                <Trash2
                                    className="h-6 w-6 pl-1 text-foreground"
                                    strokeWidth={1.5}
                                />
                            </div>
                        </DialogTitle>
                    </DialogHeader>
                    <span className="dark:text-gray-300">
                        Are you sure you want to delete this trigger?{" "}
                    </span>
                    <span className="dark:text-gray-300">
                        Note: This action is irreversible.
                    </span>
                    <div className="flex justify-end gap-4 mt-4">
                        <Button
                            variant="outline"
                            className="dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-600"
                            onClick={() => {
                                setDeleteDialogOpen(false);
                                setTriggerToDelete(null);
                            }}
                        >
                            Cancel
                        </Button>
                        <Button
                            variant="destructive"
                            onClick={() => triggerToDelete && handleDeleteTrigger(triggerToDelete)}
                        >
                            Delete
                        </Button>
                    </div>
                </DialogContent>
            </Dialog>
        </div>
    );
}