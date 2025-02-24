import { useState, useEffect } from 'react';
import { Button } from '@/components/ui/button';
import { useIntegrationStore } from '../GuidedAgentIntegrations/useIntegrationStore';
import { Badge } from '@/components/ui/badge';
import axios from 'axios';
import { AlertCircle, CheckCircle2, Mail, Play, Plus, Trash2, XCircle, Loader2, Bell, BellOff } from 'lucide-react';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Card, CardHeader, CardContent, CardDescription } from '@/components/ui/card';
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
    DialogDescription,
} from "@/components/ui/dialog";
import { motion, AnimatePresence } from 'framer-motion';
import ForwardedIconComponent from '@/components/common/genericIconComponent';
import BaseModal from '@/modals/baseModal';

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
}

interface GuidedAgentTriggersProps {
    onTriggersChange?: (triggers: string[]) => void;
    selectedTriggers: string[];
    setSelectedTriggers: React.Dispatch<React.SetStateAction<string[]>>;
}

export default function GuidedAgentTriggers({ onTriggersChange, selectedTriggers, setSelectedTriggers }: GuidedAgentTriggersProps) {
    const [integrations, setIntegrations] = useState<IntegrationDetails[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [successMessage, setSuccessMessage] = useState<string | null>(null);
    const [dialogOpen, setDialogOpen] = useState(false);
    const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
    const [triggerToDelete, setTriggerToDelete] = useState<string | null>(null);
    const axiosInstance = axios.create({
        baseURL: '/api/v1',
        headers: useIntegrationStore.getState().getAuthHeaders(),
        withCredentials: true
    });

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

    const createTrigger = async (integrationId: string) => {
        try {
            setSelectedTriggers(prev => [...prev, integrationId]);
            setSuccessMessage('Trigger set successfully');
            onTriggersChange?.([...selectedTriggers, integrationId]);
            setTimeout(() => setSuccessMessage(null), 3000);
        } catch (err) {
            setError('Failed to create trigger');
            console.error(err);
        }
    };

    const handleDeleteTrigger = (integrationId: string) => {
        setTriggerToDelete(integrationId);
        setDeleteDialogOpen(true);
    };

    const removeTrigger = (integrationId: string) => {
        const updatedTriggers = selectedTriggers.filter(id => id !== integrationId);
        setSelectedTriggers(updatedTriggers);
        onTriggersChange?.(updatedTriggers);
        setDeleteDialogOpen(false);
        setTriggerToDelete(null);
    };

    useEffect(() => {
        fetchIntegrations();
    }, []);

    const getActiveIntegrations = () => {
        return integrations.filter(integration =>
            selectedTriggers.includes(integration.id)
        );
    };

    const getInactiveIntegrations = () => {
        return integrations.filter(integration =>
            !selectedTriggers.includes(integration.id)
        );
    };

    const getStatusIcon = (status: string) => {
        switch (status) {
            case 'active':
                return <CheckCircle2 className="h-4 w-4 text-green-500" />;
            case 'expired':
                return <AlertCircle className="h-4 w-4 text-yellow-500" />;
            case 'error':
                return <XCircle className="h-4 w-4 text-red-500" />;
            default:
                return null;
        }
    };

    return (
        <div className="flex flex-1 flex-col gap-6 overflow-hidden">
            <div className="flex-none mb-4">
                <BaseModal.Header description="Enable task creation for your agent from external sources like emails or WhatsApp, allowing seamless threading into the same task.">
                    Configure Triggers

                </BaseModal.Header>
            </div>

            <div className="flex-1 overflow-y-auto space-y-6 pb-4">

                <Card>
                    <CardHeader>
                        <h3 className="text-lg font-semibold">Active Triggers</h3>
                        <CardDescription>
                            Currently active integrations that will create tasks for this agent
                        </CardDescription>
                    </CardHeader>
                    <CardContent>
                        {loading ? (
                            <div className="flex items-center justify-center py-8">
                                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                            </div>
                        ) : getActiveIntegrations().length > 0 ? (
                            <div className="grid gap-2">
                                {getActiveIntegrations().map(integration => (
                                    <motion.div
                                        key={integration.id}
                                        initial={{ opacity: 0, x: -20 }}
                                        animate={{ opacity: 1, x: 0 }}
                                        exit={{ opacity: 0, x: 20 }}
                                    >
                                        <Card className="p-3 hover:bg-muted/50 transition-colors">
                                            <div className="flex items-center justify-between">
                                                <div className="flex items-center gap-2">
                                                    <ForwardedIconComponent name="Gmail" className="h-4 w-4" />
                                                    {getStatusIcon(integration.status)}
                                                    <span className="text-sm font-medium">{integration.email}</span>
                                                </div>
                                                <Button
                                                    variant="ghost"
                                                    size="sm"
                                                    onClick={() => handleDeleteTrigger(integration.id)}
                                                    className="hover:text-destructive"
                                                >
                                                    <Trash2 className="h-4 w-4" />
                                                </Button>
                                            </div>
                                        </Card>
                                    </motion.div>
                                ))}
                            </div>
                        ) : (
                            <Card className="flex items-center justify-center p-8 text-center">
                                <div className="space-y-3">
                                    <BellOff className="mx-auto h-8 w-8 text-muted-foreground opacity-50" />
                                    <p className="text-muted-foreground">No active triggers</p>
                                </div>
                            </Card>
                        )}
                    </CardContent>
                </Card>

                <div className="space-y-2">
                    <h3 className="text-lg font-semibold px-2">Available Triggers</h3>
                    <div className="flex flex-wrap gap-4 pb-2 px-2">
                        <Card className="w-[calc(50%-0.5rem)] min-w-[300px]">
                            <CardHeader>
                                <div className="flex items-start justify-between">
                                    <div>
                                        <h3 className="text-lg font-semibold">Gmail</h3>
                                        <CardDescription>
                                            Connect Gmail accounts to create automated workflows
                                        </CardDescription>
                                    </div>
                                    <ForwardedIconComponent name="Gmail" className="h-6 w-6" />
                                </div>
                            </CardHeader>
                            <CardContent>
                                <Button
                                    variant="outline"
                                    className="w-full justify-start gap-2 hover:bg-muted"
                                    onClick={() => setDialogOpen(true)}
                                >
                                    <Plus className="h-4 w-4" />
                                    Add Gmail Trigger
                                </Button>
                            </CardContent>
                        </Card>

                        <Card className="w-[calc(50%-0.5rem)] min-w-[300px]">
                            <CardHeader>
                                <div className="flex items-start justify-between">
                                    <div>
                                        <h3 className="text-lg font-semibold">WhatsApp</h3>
                                        <CardDescription>
                                            Connect WhatsApp accounts to create automated workflows
                                        </CardDescription>
                                    </div>
                                    <ForwardedIconComponent name="WhatsApp" className="h-6 w-6" />
                                </div>
                            </CardHeader>
                            <CardContent>
                                <Button
                                    variant="outline"
                                    className="w-full justify-start gap-2 hover:bg-muted"
                                >
                                    <Plus className="h-4 w-4" />
                                    Add WhatsApp Trigger
                                </Button>
                            </CardContent>
                        </Card>

                    </div>
                </div>
            </div>

            <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
                <DialogContent className="max-w-xl">
                    <DialogHeader>
                        <DialogTitle>Select Gmail Account</DialogTitle>
                        <DialogDescription>
                            Choose an account to create a new trigger
                        </DialogDescription>
                    </DialogHeader>

                    <div className="max-h-[60vh] overflow-y-auto">
                        <div className="space-y-4 pr-4">

                            {getInactiveIntegrations().length === 0 ? (
                                <Card className="flex items-center justify-center p-4 text-center">
                                    <div className="space-y-3">
                                        <Mail className="mx-auto h-12 w-12 text-muted-foreground opacity-50" />
                                        <p className="text-muted-foreground">No available Gmail accounts</p>
                                    </div>
                                </Card>
                            ) : (
                                getInactiveIntegrations().map((integration) => (
                                    <Card key={integration.id} className="p-4">
                                        <div className="flex items-start justify-between">
                                            <div className="space-y-3">
                                                <div className="flex items-center gap-2">
                                                    {getStatusIcon(integration.status)}
                                                    <span className="font-medium">{integration.email}</span>
                                                </div>
                                                <div className="flex flex-wrap gap-2">
                                                    {integration.permissions.map((permission) => (
                                                        <Badge
                                                            key={permission}
                                                            variant="secondary"
                                                            className="text-xs"
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
                                                    createTrigger(integration.id);
                                                    setDialogOpen(false);
                                                }}
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

            <Dialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
                <DialogContent>
                    <DialogHeader>
                        <DialogTitle>
                            <div className="flex items-center">
                                <span className="pr-2">Delete Trigger</span>
                                <Trash2
                                    className="h-6 w-6 pl-1 text-foreground"
                                    strokeWidth={1.5}
                                />
                            </div>
                        </DialogTitle>
                    </DialogHeader>
                    <span>
                        Are you sure you want to delete this trigger?{" "}
                    </span>
                    <span>
                        Note: This action is irreversible.
                    </span>
                    <div className="flex justify-end gap-4 mt-4">
                        <Button
                            variant="outline"

                            onClick={() => {
                                setDeleteDialogOpen(false);
                                setTriggerToDelete(null);
                            }}
                        >
                            Cancel
                        </Button>
                        <Button
                            variant="destructive"
                            onClick={() => triggerToDelete && removeTrigger(triggerToDelete)}
                        >
                            Delete
                        </Button>
                    </div>
                </DialogContent>
            </Dialog>
        </div >
    );
}