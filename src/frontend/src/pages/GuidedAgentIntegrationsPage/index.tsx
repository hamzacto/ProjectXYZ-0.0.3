import { useNavigate } from 'react-router-dom';
import PageLayout from '../../components/common/pageLayout';
import ForwardedIconComponent from '@/components/common/genericIconComponent';
import { Button } from '@/components/ui/button';
import { ChevronRight } from 'lucide-react';
import { SlackIcon } from '@/icons/Slack';
import { HubSpotIcon } from '@/icons/HubSpot/hubspot';

export default function GuidedAgentIntegrationsPage(): JSX.Element {
  const navigate = useNavigate();

  return (
    <PageLayout
      title="Integrations"
      description="Manage your third-party app integrations and their permissions"
    >
      <div className="mx-auto w-full space-y-6 flex h-full w-full flex-col">
        <div className="border rounded-lg divide-y">
          <div className="p-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-4">
                <ForwardedIconComponent name="Google" className="h-8 w-8" />
                <div>
                  <h3 className="text-lg font-medium">Google Workspace</h3>
                  <p className="text-sm text-muted-foreground">
                    Connect your Google Workspace account to enable email, calendar, and sheets capabilities
                  </p>
                </div>
              </div>
              <Button 
                variant="ghost"
                onClick={() => navigate('/integrations/gmail')}
                className="gap-2"
              >
                Configure
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
          
          <div className="p-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-4">
                <ForwardedIconComponent name="Slack" className="h-8 w-8" />
                <div>
                  <h3 className="text-lg font-medium">Slack</h3>
                  <p className="text-sm text-muted-foreground">
                    Connect to Slack to enable messaging capabilities
                  </p>
                </div>
              </div>
              <Button 
                variant="ghost"
                onClick={() => navigate('/integrations/slack')}
                className="gap-2"
              >
                Configure
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
          
          <div className="p-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-4">
                <ForwardedIconComponent name="HubSpot" className="h-8 w-8" />
                <div>
                  <h3 className="text-lg font-medium">HubSpot</h3>
                  <p className="text-sm text-muted-foreground">
                    Connect to HubSpot CRM to access contacts, companies, and deals
                  </p>
                </div>
              </div>
              <Button 
                variant="ghost"
                onClick={() => navigate('/integrations/hubspot')}
                className="gap-2"
              >
                Configure
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </div>
      </div>
    </PageLayout>
  );
}