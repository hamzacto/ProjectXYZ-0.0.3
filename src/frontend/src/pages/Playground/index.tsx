import { useGetFlow } from "@/controllers/API/queries/flows/use-get-flow";
import { useCustomNavigate } from "@/customization/hooks/use-custom-navigate";
import { track } from "@/customization/utils/analytics";
import IOModal from "@/modals/IOModal/new-modal";
import { useStoreStore } from "@/stores/storeStore";
import { useEffect } from "react";
import { useParams } from "react-router-dom";
import { getComponent } from "../../controllers/API";
import useFlowsManagerStore from "../../stores/flowsManagerStore";
import cloneFLowWithParent from "../../utils/storeUtils";

export default function PlaygroundPage() {
  const setCurrentFlow = useFlowsManagerStore((state) => state.setCurrentFlow);
  const currentSavedFlow = useFlowsManagerStore((state) => state.currentFlow);
  const flowToCanvas = useFlowsManagerStore((state) => state.flowToCanvas);
  const setFlowToCanvas = useFlowsManagerStore((state) => state.setFlowToCanvas);
  const validApiKey = useStoreStore((state) => state.validApiKey);
  const { id } = useParams();
  const { mutateAsync: getFlow } = useGetFlow();

  const navigate = useCustomNavigate();

  const currentFlowId = useFlowsManagerStore((state) => state.currentFlowId);
  const setIsLoading = useFlowsManagerStore((state) => state.setIsLoading);

  // Clean up flowToCanvas when unmounting to prevent stale data
  useEffect(() => {
    return () => {
      setFlowToCanvas(null);
      setCurrentFlow(undefined);
      setIsLoading(false);
    };
  }, [setFlowToCanvas, setCurrentFlow, setIsLoading]);

  async function getFlowData() {
    try {
      const flow = await getFlow({ id: id! });
      return flow;
    } catch (error: any) {
      if (error?.response?.status === 404) {
        if (!validApiKey) {
          return null;
        }
        try {
          const res = await getComponent(id!);
          const newFlow = cloneFLowWithParent(res, res.id, false, true);
          return newFlow;
        } catch (componentError) {
          return null;
        }
      }
      return null;
    }
  }

  useEffect(() => {
    const initializeFlow = async () => {
      setIsLoading(true);
      
      // First check if we have a flowToCanvas and if it matches the current id
      if (flowToCanvas && flowToCanvas.id === id) {
        // Use the flowToCanvas data that was set when clicking the list item
        setCurrentFlow(flowToCanvas);
        setIsLoading(false);
      } else if (currentFlowId === "") {
        // Fall back to fetching from API if no flowToCanvas or id mismatch
        const flow = await getFlowData();
        if (flow) {
          setCurrentFlow(flow);
        } else {
          navigate("/");
        }
        setIsLoading(false);
      } else {
        setIsLoading(false);
      }
    };

    initializeFlow();
  }, [id, validApiKey, flowToCanvas]); // Add flowToCanvas as a dependency

  useEffect(() => {
    if (id) track("Playground Page Loaded", { flowId: id });
  }, []);

  return (
    <div className="flex h-full w-full flex-col items-center justify-center align-middle">
      {currentSavedFlow && (
        <IOModal open={true} setOpen={() => {}} isPlayground>
          <></>
        </IOModal>
      )}
    </div>
  );
}
