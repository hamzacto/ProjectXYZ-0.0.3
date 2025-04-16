import { memo, useCallback, useEffect, useState } from "react";
import { ForwardedIconComponent } from "@/components/common/genericIconComponent";
import { SidebarProvider } from "@/components/ui/sidebar";
import ToolsLinkSidebarItemsList from "@/pages/FlowPage/components/flowSidebarComponent/components/toolsLinkSideBarItemList";
import { AddedToolsList } from "@/pages/FlowPage/components/flowSidebarComponent/components/AddedToolsList";
import { APIClassType } from "@/types/api";
import { cn } from "@/utils/utils";
import { Badge } from "@/components/ui/badge";
import axios from "axios";
import useAuthStore from "@/stores/authStore";
import "./index.css";

// Type definitions
interface CategoryItem {
  name: string;
  display_name: string;
  icon: string;
}

interface ToolsLinkCategoryDisclosureProps {
  item: CategoryItem;
  openCategories: string[];
  setOpenCategories: React.Dispatch<React.SetStateAction<string[]>>;
  dataFilter: Record<string, any>;
  nodeColors: Record<string, string>;
  chatInputAdded: boolean;
  onDragStart: (
    event: React.DragEvent<HTMLDivElement>,
    data: { type: string; node?: APIClassType }
  ) => void;
  sensitiveSort: (a: any, b: any) => number;
  addTool: (tool: any) => void;
  addedTools: any[];
  deleteTool: (tool: any) => void;
}

// Interface for connected services
interface IntegrationStatus {
  service_name: string;
  connected: boolean;
  status: string;
}

export const ToolsLinkCategoryDisclosure = memo(function ToolsLinkCategoryDisclosure({
  item,
  openCategories,
  setOpenCategories,
  dataFilter,
  nodeColors,
  chatInputAdded,
  onDragStart,
  sensitiveSort,
  addTool,
  addedTools,
  deleteTool,
}: ToolsLinkCategoryDisclosureProps) {
  const [connectedServices, setConnectedServices] = useState<IntegrationStatus[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [hasError, setHasError] = useState(false);
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  const accessToken = useAuthStore((state) => state.accessToken);

  // Fetch connected services on component mount
  useEffect(() => {
    const fetchConnectedServices = async () => {
      try {
        setIsLoading(true);
        setHasError(false);
        
        // Get the access token from cookie (same pattern used in GmailIntegrationsDetailPage)
        const cookieToken = document.cookie
          .split('; ')
          .find(row => row.startsWith('access_token_lf='))
          ?.split('=')[1];
          
        // Create axios instance with auth headers
        const axiosInstance = axios.create({
          baseURL: '/api/v1',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${cookieToken || accessToken}`
          },
          withCredentials: true // Important: allows cookies to be sent with the request
        });
        
        const response = await axiosInstance.get('/integration/status');
        
        if (response.data && response.data.integrations) {
          setConnectedServices(response.data.integrations);
        }
      } catch (error) {
        console.error("Error fetching integration status:", error);
        setHasError(true);
        setConnectedServices([]); // Reset connected services on error
      } finally {
        setIsLoading(false);
      }
    };

    if (isAuthenticated) {
      fetchConnectedServices();
    } else {
      setIsLoading(false);
      setHasError(true);
    }
  }, [isAuthenticated, accessToken]);

  const handleKeyDownInput = useCallback(
    (e: React.KeyboardEvent<HTMLDivElement>) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        setOpenCategories((prev) =>
          prev.includes(item.name)
            ? prev.filter((cat) => cat !== item.name)
            : [...prev, item.name]
        );
      }
    },
    [item.name, setOpenCategories]
  );

  const handleAddTool = useCallback(
    (tool) => {
      if (!addedTools.includes(tool)) {
        addTool(tool);
      }
    },
    [addedTools, addTool]
  );

  const getTotalToolsCount = () => {
    return Object.values(dataFilter[item.name] || {}).length;
  };

  // Helper function to check if a service is connected
  const isServiceConnected = useCallback((serviceName: string) => {
    // If error occurred or still loading, assume services are connected to avoid 
    // showing warnings unnecessarily
    if (isLoading || hasError) return true;
    
    // Normalize service names for easier comparison
    const normalizedServiceName = serviceName.toLowerCase();
    
    if (normalizedServiceName.includes('hubspot')) {
      return connectedServices.some(service => 
        service.service_name === 'hubspot' && service.connected);
    }
    
    if (normalizedServiceName.includes('slack')) {
      return connectedServices.some(service => 
        service.service_name === 'slack' && service.connected);
    }
    
    if (normalizedServiceName.includes('gmail') || normalizedServiceName.includes('google')) {
      return connectedServices.some(service => 
        service.service_name === 'gmail' && service.connected);
    }
    
    return true; // Return true for services that don't require connections
  }, [connectedServices, isLoading, hasError]);

  return (
    <div className="tools-link-category-container">
      {/* Left Panel - Available Tools */}
      <div className={cn(
        "flex-1 overflow-hidden rounded-lg border bg-background",
        "min-w-0"
      )}>
        <div className="tools-link-category">
          <div className="border-b px-4 py-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <ForwardedIconComponent 
                  name={item.icon || "Hammer"} 
                  className="h-4 w-4 text-primary" 
                />
                <span className="text-sm font-medium">Available Tools</span>
              </div>
              <Badge variant="secondary" className="h-5 px-2 text-xs">
                {getTotalToolsCount() - 23} available
              </Badge>
            </div>
          </div>
          <div className="flex-1 overflow-y-auto p-2">
            <ToolsLinkSidebarItemsList
              item={item}
              dataFilter={dataFilter}
              nodeColors={nodeColors}
              chatInputAdded={chatInputAdded}
              onDragStart={onDragStart}
              sensitiveSort={sensitiveSort}
              onAddTool={handleAddTool}
              addedTools={addedTools}
              addTool={addTool}
              isServiceConnected={isServiceConnected}
            />
          </div>
        </div>
      </div>

      {/* Right Panel - Added Tools */}
      <div className="w-[300px]">
        <SidebarProvider>
          <AddedToolsList 
            tools={addedTools} 
            deleteTool={deleteTool}
            isServiceConnected={isServiceConnected} 
          />
        </SidebarProvider>
      </div>
    </div>
  );
});

ToolsLinkCategoryDisclosure.displayName = "ToolsLinkCategoryDisclosure";