import { useNavigate } from 'react-router-dom';
import PageLayout from '../../components/common/pageLayout';
import { Button } from '@/components/ui/button';
import { Plus } from 'lucide-react';
import { useState, useEffect } from 'react';
import { useIntegrationStore } from '@/modals/templatesModal/components/GuidedAgentIntegrations/useIntegrationStore';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription } from '@/components/ui/alert';
import axios from 'axios';
import { CheckCircle2, AlertCircle, XCircle } from 'lucide-react';
import { Card } from '@/components/ui/card';
import { HubSpotIcon } from '@/icons/HubSpot/hubspot';

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
        hub_domain?: string;
        hub_id?: string;
        account_type?: string;
        portal_id?: string;
        [key: string]: any;
    };
}

export default function HubSpotIntegrationsDetailPage() {
    const navigate = useNavigate();
    const [integrations, setIntegrations] = useState<IntegrationDetails[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const { setHubSpotConnected } = useIntegrationStore();

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
            const hubspotIntegrations = response.data.integrations.filter(
                (integration: IntegrationDetails) => integration.service_name === 'hubspot'
            );
            setIntegrations(hubspotIntegrations);
            setHubSpotConnected(hubspotIntegrations.length > 0);
        } catch (err) {
            setError('Failed to fetch integrations');
            console.error(err);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        const messageHandler = (event: MessageEvent) => {
            if (event.data && event.data.hubspotConnected) {
                setHubSpotConnected(true);
                fetchIntegrations();
            }
            // Handle authentication errors
            if (event.data && event.data.hubspotError) {
                setError(`HubSpot authentication error: ${event.data.hubspotError}`);
            }
        };

        window.addEventListener('message', messageHandler);
        fetchIntegrations();

        return () => {
            window.removeEventListener('message', messageHandler);
        };
    }, [setHubSpotConnected]);

    const deleteIntegration = async (integrationId: string) => {
        try {
            const headers = useIntegrationStore.getState().getAuthHeaders();
            await axiosInstance.delete(`/integration/hubspot?service_name=hubspot`, { headers });
            setHubSpotConnected(false);
            await fetchIntegrations();
        } catch (err) {
            setError('Failed to delete integration');
            console.error(err);
        }
    };

    const connectHubSpot = () => {
        const hubspotWindow = window.open(`/api/v1/auth/hubspot/login`, 'hubspot_auth', 'width=800,height=800');
        
        window.addEventListener('message', async (event) => {
            if (event.data && event.data.hubspotConnected) {
                await fetchIntegrations();
                if (hubspotWindow) hubspotWindow.close();
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

    const getHubSpotPermissions = (permissions: string[] = []) => {
        const defaultPermissions = [
            "contacts",
            "companies",
            "deals"
        ];
        return permissions.length > 0 ? permissions : defaultPermissions;
    };

    return (
        <PageLayout
            title="HubSpot Integration Details"
            description="Manage your connected HubSpot accounts and their permissions"
            button={
                <Button onClick={connectHubSpot} className="gap-2">
                    <Plus className="h-4 w-4" />
                    Connect HubSpot
                </Button>
            }
            backTo="/integrations"
        >
            <div className="mx-auto w-full space-y-6 flex h-full w-full flex-col">

                <div>
                    <p className="text-sm text-muted-foreground mt-1">
                        {integrations.length} {integrations.length === 1 ? 'account' : 'accounts'} connected
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
                                        <HubSpotIcon/>
                                    </div>
                                    <p className="text-muted-foreground mt-3">No HubSpot accounts connected</p>
                                    <p className="text-xs text-muted-foreground max-w-md mx-auto">
                                        Connect HubSpot to enable your AI agents to interact with your CRM data, including contacts, companies, and deals.
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
                                                        {integration.integration_metadata?.hub_domain || 
                                                         integration.email || 
                                                         "HubSpot Account"}
                                                    </span>
                                                    {integration.integration_metadata?.account_type && (
                                                        <Badge variant="outline" className="ml-2 text-xs capitalize">
                                                            {integration.integration_metadata.account_type}
                                                        </Badge>
                                                    )}
                                                </div>
                                                <div className="flex flex-wrap gap-2">
                                                    {getHubSpotPermissions(integration.permissions).map((permission) => (
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
                                                onClick={() => deleteIntegration(integration.id)}
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
