import React, { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { useIntegrationStore } from './useIntegrationStore';
import ForwardedIconComponent from '@/components/common/genericIconComponent';
import { Badge } from '@/components/ui/badge';
import axios from 'axios';
import { AlertCircle, CheckCircle2, Mail, Plus, XCircle } from 'lucide-react';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Card } from '@/components/ui/card';

interface IntegrationDetails {
    service_name: string;
    connected: boolean;
    created_at: string;
    updated_at: string;
    expires_at: string | null;
    permissions: string[];
    email: string | null;
    status: 'active' | 'expired' | 'error';
}

export default function GuidedAgentIntegrations() {
    const [integrations, setIntegrations] = useState<IntegrationDetails[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const { setGmailConnected } = useIntegrationStore();

    const fetchIntegrations = async () => {
        setLoading(true);
        setError(null);
        try {
            const headers = useIntegrationStore.getState().getAuthHeaders();
            const response = await axios.get('/api/v1/integration/status', { headers });
            setIntegrations(response.data.integrations);
        } catch (err) {
            setError('Failed to fetch integrations');
            console.error(err);
        } finally {
            setLoading(false);
        }
    };

    const deleteIntegration = async () => {
        try {
            const headers = useIntegrationStore.getState().getAuthHeaders();
            await axios.delete(`/api/v1/integration/gmail`, { headers });
            setGmailConnected(false);
            await fetchIntegrations();
        } catch (err) {
            setError('Failed to delete integration');
            console.error(err);
        }
    };

    const connectGmail = () => {
        const gmailWindow = window.open(`/api/v1/auth/login`, 'gmail_auth', 'width=600,height=600');
        
        window.addEventListener('message', async (event) => {
            if (event.data === 'gmail_connected') {
                await fetchIntegrations();
                if (gmailWindow) gmailWindow.close();
            }
        }, { once: true });
    };

    useEffect(() => {
        fetchIntegrations();
    }, []);

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
        <div className="space-y-6">
            <div className="flex items-center justify-between">
                <div>
                    <h2 className="text-lg font-semibold">Gmail Integrations</h2>
                    <p className="text-sm text-muted-foreground">
                        {integrations.length} {integrations.length === 1 ? 'account' : 'accounts'} connected
                    </p>
                </div>
                <Button onClick={connectGmail} className="gap-2">
                    <Plus className="h-4 w-4" />
                    Connect Gmail
                </Button>
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
                <div className="space-y-4">
                    {integrations.length === 0 ? (
                        <Card className="flex items-center justify-center p-8 text-center">
                            <div className="space-y-3">
                                <Mail className="mx-auto h-8 w-8 text-muted-foreground" />
                                <p className="text-sm text-muted-foreground">No Gmail accounts connected</p>
                            </div>
                        </Card>
                    ) : (
                        integrations.map((integration) => (
                            <Card key={integration.email} className="p-4">
                                <div className="flex items-start justify-between">
                                    <div className="space-y-3">
                                        <div className="flex items-center gap-2">
                                            {getStatusIcon(integration.status)}
                                            <span className="font-medium">{integration.email}</span>
                                        </div>
                                        <div className="flex flex-wrap gap-2">
                                            {integration.permissions.map((permission) => (
                                                <Badge key={permission} variant="secondary" className="text-xs">
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
                        ))
                    )}
                </div>
            )}
        </div>
    );
}