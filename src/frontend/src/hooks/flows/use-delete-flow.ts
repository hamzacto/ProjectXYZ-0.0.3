import { useDeleteDeleteFlows } from "@/controllers/API/queries/flows/use-delete-delete-flows";
import useFlowsManagerStore from "@/stores/flowsManagerStore";
import { useTypesStore } from "@/stores/typesStore";
import { useFlowWizardMetadata } from "@/hooks/flows/use-flow-wizard-metadata";
import { useIntegrationStore } from "@/stores/integrationStore";
import axios from "axios";
import {
  extractFieldsFromComponenents,
  processFlows,
} from "@/utils/reactflowUtils";

const useDeleteFlow = () => {
  const flows = useFlowsManagerStore((state) => state.flows);
  const setFlows = useFlowsManagerStore((state) => state.setFlows);
  const { getFlowWizardMetadata } = useFlowWizardMetadata();

  const { mutate, isPending } = useDeleteDeleteFlows();

  // Utility function to clean up associated resources
  const cleanupFlowResources = async (flowId: string) => {
    try {
      // Get the flow's wizard metadata
      const metadata = await getFlowWizardMetadata(flowId);

      if (metadata) {
        // Create axios instance for API calls
        const axiosInstance = axios.create({
          baseURL: '/api/v1',
          headers: useIntegrationStore.getState().getAuthHeaders(),
          withCredentials: true
        });

        // 1. Clean up triggers
        if (metadata.triggers && metadata.triggers.length > 0) {
          for (const triggerInfo of metadata.triggers) {
            try {
              // Parse the trigger info (format: "service_name:integration_id")
              const [serviceName, integrationId] = triggerInfo.split(':');
              
              // Call the appropriate unwatch endpoint based on the service name
              if (serviceName === 'gmail') {
                await axiosInstance.post(`/gmail/watch/${integrationId}`, {
                  integration_id: integrationId,
                  flow_id: flowId
                });
                await axiosInstance.delete(`/integrations/trigger/${integrationId}/${flowId}`);
              } else if (serviceName === 'slack') {
                await axiosInstance.post(`/slack/unwatch/${integrationId}`, {
                  integration_id: integrationId,
                  flow_id: flowId
                });
                await axiosInstance.delete(`/integrations/trigger/${integrationId}/${flowId}`);
              } else if (serviceName === 'hubspot') {
                await axiosInstance.post(`/hubspot/unwatch/${integrationId}`, {
                  integration_id: integrationId,
                  flow_id: flowId
                });
                await axiosInstance.delete(`/integrations/trigger/${integrationId}/${flowId}`);
              }
            } catch (error) {
              console.error('Failed to remove trigger:', triggerInfo, error);
              // Continue with other triggers even if one fails
            }
          }
        }

        // 2. Clean up knowledge base files
        if (metadata.knowledgeBase?.categories && metadata.collectionName) {
          const allFiles = metadata.knowledgeBase.categories.flatMap(category => category.files);
          for (const file of allFiles) {
            try {
              await axiosInstance.delete(`/milvus/files/${metadata.collectionName}/${file.id}`);
            } catch (error) {
              console.error(`Error deleting file ${file.id}:`, error);
              // Continue with other files even if one fails
            }
          }
        }

        // 3. Delete the wizard metadata itself
        try {
          await axiosInstance.delete(`/flow-wizard-metadata/${flowId}`);
        } catch (error) {
          console.error('Failed to delete wizard metadata:', error);
        }
      }
    } catch (error) {
      console.error('Error during flow resource cleanup:', error);
    }
  };

  const deleteFlow = async ({
    id,
  }: {
    id: string | string[];
  }): Promise<void> => {
    return new Promise<void>(async (resolve, reject) => {
      if (!Array.isArray(id)) {
        id = [id];
      }

      try {
        // Clean up resources for each flow before deletion
        for (const flowId of id) {
          await cleanupFlowResources(flowId);
        }

        // Delete the flows
        mutate(
          { flow_ids: id },
          {
            onSuccess: () => {
              const { data, flows: myFlows } = processFlows(
                (flows ?? []).filter((flow) => !id.includes(flow.id)),
              );
              setFlows(myFlows);
              useTypesStore.setState((state) => ({
                data: { ...state.data, ["saved_components"]: data },
                ComponentFields: extractFieldsFromComponenents({
                  ...state.data,
                  ["saved_components"]: data,
                }),
              }));

              resolve();
            },
            onError: (e) => reject(e),
          },
        );
      } catch (error) {
        reject(error);
      }
    });
  };

  return { deleteFlow, isDeleting: isPending };
};

export default useDeleteFlow;
