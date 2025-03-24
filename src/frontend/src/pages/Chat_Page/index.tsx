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
import ChatModal from "../ChatPage";

export default function ChatPage() {
  const setCurrentFlow = useFlowsManagerStore((state) => state.setCurrentFlow);
  const currentSavedFlow = useFlowsManagerStore((state) => state.currentFlow);
  const validApiKey = useStoreStore((state) => state.validApiKey);
  const { id } = useParams();
  const { mutateAsync: getFlow } = useGetFlow();

  const navigate = useCustomNavigate();

  const currentFlowId = useFlowsManagerStore((state) => state.currentFlowId);
  const setIsLoading = useFlowsManagerStore((state) => state.setIsLoading);

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
      if (currentFlowId === "") {
        const flow = await getFlowData();
        if (flow) {
          setCurrentFlow(flow);
        } else {
          navigate("/");
        }
      }
    };

    initializeFlow();
    setIsLoading(false);
  }, [id, validApiKey]);

  useEffect(() => {
    if (id) track("Chat Page Loaded", { flowId: id });
  }, []);

  return (
    <div className="flex h-full w-full flex-col items-center justify-center align-middle">
      {currentSavedFlow && (
        <ChatModal open={true} setOpen={() => {}} isPlayground>
          <></>
        </ChatModal>
      )}
    </div>
  );
}
