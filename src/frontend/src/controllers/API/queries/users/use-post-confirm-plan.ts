import { useMutation, UseMutationResult } from "@tanstack/react-query";
import { api } from "../../api";
import { getURL } from "../../helpers/constants";
import { UseRequestProcessor } from "../../services/request-processor";

// Define response type if needed, though simple success/error might suffice
interface ConfirmPlanResponse {
  message: string;
}

export function useConfirmPlanSelection(): UseMutationResult<
  ConfirmPlanResponse,
  unknown, // Error type
  void, // Variables type (none needed)
  unknown // Context type
> {
  const { mutate } = UseRequestProcessor();

  const confirmPlanFn = async (): Promise<ConfirmPlanResponse> => {
    const response = await api.post(
      `${getURL("USERS")}/confirm-plan-selection`,
    );
    return response.data;
  };

  return mutate([
    "confirmPlanSelection" // Unique query key
  ], confirmPlanFn, {
    // Optional: Add onSuccess/onError handlers if needed globally
  });
} 