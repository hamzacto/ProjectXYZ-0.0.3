import axios from "axios";
import useAlertStore from "@/stores/alertStore";
import { useState } from "react";
import { useIntegrationStore } from "@/stores/integrationStore";

export function useFlowWizardMetadata() {
  const [loading, setLoading] = useState(false);
  const [metadata, setMetadata] = useState<Record<string, any> | null>(null);
  const setErrorData = useAlertStore((state) => state.setErrorData);

  const getFlowWizardMetadata = async (flowId: string) => {
    setLoading(true);
    try {
      const response = await axios.get(`/api/v1/flow-wizard-metadata/${flowId}`, {
        headers: useIntegrationStore.getState().getAuthHeaders(),
        withCredentials: true
      });
      console.log("Flow wizard metadata response:", response.data);
      setMetadata(response.data.wizard_metadata);
      return response.data.wizard_metadata;
    } catch (error: any) {
      console.error("Error fetching flow wizard metadata:", error);
      // Don't show error if metadata doesn't exist (404)
      if (error.response?.status !== 404) {
        setErrorData({
          title: "Error fetching flow wizard metadata",
          list: [error.message || "Unknown error"],
        });
      }
      setMetadata(null);
      return null;
    } finally {
      setLoading(false);
    }
  };

  const updateFlowWizardMetadata = async (flowId: string, metadata: Record<string, any>) => {
    setLoading(true);
    try {
      const response = await axios.post(`/api/v1/flow-wizard-metadata/${flowId}`, {
        wizard_metadata: metadata,
      }, {
        headers: useIntegrationStore.getState().getAuthHeaders(),
        withCredentials: true
      });
      console.log("Updated flow wizard metadata response:", response.data);
      setMetadata(response.data.wizard_metadata);
      return response.data.wizard_metadata;
    } catch (error: any) {
      console.error("Error updating flow wizard metadata:", error);
      setErrorData({
        title: "Error updating flow wizard metadata",
        list: [error.message || "Unknown error"],
      });
      return null;
    } finally {
      setLoading(false);
    }
  };

  return {
    loading,
    metadata,
    getFlowWizardMetadata,
    updateFlowWizardMetadata,
  };
}
