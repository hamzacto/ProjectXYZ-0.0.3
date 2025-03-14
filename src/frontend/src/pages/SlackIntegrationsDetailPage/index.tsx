import { useNavigate } from 'react-router-dom';
import PageLayout from '../../components/common/pageLayout';
import { Button } from '@/components/ui/button';
import { ChevronLeft, Plus } from 'lucide-react';
import { useState, useEffect } from 'react';
import { useIntegrationStore } from '@/modals/templatesModal/components/GuidedAgentIntegrations/useIntegrationStore';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription } from '@/components/ui/alert';
import axios from 'axios';
import { CheckCircle2, AlertCircle, XCircle } from 'lucide-react';
import { Card } from '@/components/ui/card';
import { SlackIcon } from '@/icons/Slack';

interface IntegrationDetails {
    service_name: string;
    connected: boolean;
    created_at: string;
    updated_at: string;
    expires_at: string | null;
    permissions: string[];
    email_address: string | null;
    status: 'active' | 'expired' | 'error';
    integration_metadata?: {
        user_display_name?: string;
        team_name?: string;
        [key: string]: any;
    };
}

export default function SlackIntegrationsDetailPage() {
    const navigate = useNavigate();
    const [integrations, setIntegrations] = useState<IntegrationDetails[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const { setSlackConnected } = useIntegrationStore();

    const axiosInstance = axios.create({
        baseURL: '/api/v1',
        headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${document.cookie
                .split('; ')
                .find(row => row.startsWith('access_token_lf='))
                ?.split('=')[1]}`
        },
        withCredentials: true
    });

    const fetchIntegrations = async () => {
        setLoading(true);
        setError(null);
        try {
            const response = await axiosInstance.get('/integration/status');
            const slackIntegrations = response.data.integrations.filter(
                (integration: IntegrationDetails) => integration.service_name === 'slack'
            );
            setIntegrations(slackIntegrations);
            setSlackConnected(slackIntegrations.length > 0);
        } catch (err) {
            setError('Failed to fetch integrations');
            console.error(err);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        const messageHandler = (event: MessageEvent) => {
            if (event.data && event.data.slackConnected) {
                setSlackConnected(true);
                fetchIntegrations();
            }
            // Handle authentication errors
            if (event.data && event.data.slackError) {
                setError(`Slack authentication error: ${event.data.slackError}`);
            }
        };

        window.addEventListener('message', messageHandler);
        fetchIntegrations();

        return () => {
            window.removeEventListener('message', messageHandler);
        };
    }, [setSlackConnected]);

    const deleteIntegration = async () => {
        try {
            const headers = useIntegrationStore.getState().getAuthHeaders();
            await axios.delete(`/api/v1/integration/slack`, { headers });
            setSlackConnected(false);
            await fetchIntegrations();
        } catch (err) {
            setError('Failed to delete integration');
            console.error(err);
        }
    };

    const connectSlack = () => {
        const slackWindow = window.open(`/api/v1/auth/slack/login`, 'slack_auth', 'width=600,height=600');
        
        window.addEventListener('message', async (event) => {
            if (event.data && event.data.slackConnected) {
                await fetchIntegrations();
                if (slackWindow) slackWindow.close();
            }
        }, { once: true });
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

    const getSlackPermissions = (permissions: string[] = []) => {
        const defaultPermissions = [
            "send_messages",
            "read_messages",
            "manage_channels"
        ];
        return permissions.length > 0 ? permissions : defaultPermissions;
    };

    return (
        <PageLayout
            title="Slack Integration Details"
            description="Manage your connected Slack workspaces and their permissions"
            button={
                <Button onClick={connectSlack} className="gap-2">
                    <Plus className="h-4 w-4" />
                    Connect Slack
                </Button>
            }
            backTo="/integrations"
        >
            <div className="mx-auto w-full space-y-6 flex h-full w-full flex-col">

                <div>
                    <p className="text-sm text-muted-foreground mt-1">
                        {integrations.length} {integrations.length === 1 ? 'workspace' : 'workspaces'} connected
                    </p>
                </div>

                {error && (
                    <Alert variant="destructive">
                        <AlertDescription>{error}</AlertDescription>
                    </Alert>
                )}

                {loading ? (
                    <div className="flex justify-center py-8">
                        <span className="text-muted-foreground">Loading integrations...</span>
                    </div>
                ) : (
                    <div>
                        {integrations.length === 0 ? (
                            <Card className="flex items-center justify-center p-8 text-center">
                                <div className="space-y-3">
                                    <div className="mx-auto flex justify-center opacity-50">
                                        <SlackIcon />
                                    </div>
                                    <p className="text-muted-foreground mt-3">No Slack workspaces connected</p>
                                    <p className="text-xs text-muted-foreground max-w-md mx-auto">
                                        Connect Slack to enable your AI agents to interact with your Slack channels and direct messages.
                                    </p>
                                </div>
                            </Card>
                        ) : (
                            <div className="grid gap-4">
                                {integrations.map((integration, index) => (
                                    <Card key={index} className="p-6">
                                        <div className="flex items-start justify-between">
                                            <div className="space-y-3">
                                                <div className="flex items-center gap-2">
                                                    {getStatusIcon(integration.status)}
                                                    <span className="font-medium">
                                                        {integration.email_address || 
                                                         (integration.integration_metadata?.user_display_name ? 
                                                          `${integration.integration_metadata.user_display_name}` : 
                                                          "Slack Workspace")}
                                                    </span>
                                                </div>
                                                <div className="flex flex-wrap gap-2">
                                                    {getSlackPermissions(integration.permissions).map((permission) => (
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
                                                variant="ghost"
                                                size="sm"
                                                onClick={deleteIntegration}
                                                className="text-destructive hover:text-destructive hover:bg-destructive/10"
                                            >
                                                Remove
                                            </Button>
                                        </div>
                                    </Card>
                                ))}
                            </div>
                        )}
                    </div>
                )}
            </div>
        </PageLayout>
    );
} 