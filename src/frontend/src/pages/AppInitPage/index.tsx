import { useGetAutoLogin } from "@/controllers/API/queries/auth";
import { useGetConfig } from "@/controllers/API/queries/config/use-get-config";
import { useGetBasicExamplesQuery } from "@/controllers/API/queries/flows/use-get-basic-examples";
import { useGetTypes } from "@/controllers/API/queries/flows/use-get-types";
import { useGetFoldersQuery } from "@/controllers/API/queries/folders/use-get-folders";
import { useGetTagsQuery } from "@/controllers/API/queries/store";
import { useGetGlobalVariables } from "@/controllers/API/queries/variables";
import { useGetVersionQuery } from "@/controllers/API/queries/version";
import { CustomLoadingPage } from "@/customization/components/custom-loading-page";
import { useCustomPrimaryLoading } from "@/customization/hooks/use-custom-primary-loading";
import { useDarkStore } from "@/stores/darkStore";
import useFlowsManagerStore from "@/stores/flowsManagerStore";
import { useEffect } from "react";
import { Outlet, useNavigate, useLocation } from "react-router-dom";
import { LoadingPage } from "../LoadingPage";
import useAuthStore from "@/stores/authStore";

export function AppInitPage() {
  const dark = useDarkStore((state) => state.dark);
  const refreshStars = useDarkStore((state) => state.refreshStars);
  const isLoading = useFlowsManagerStore((state) => state.isLoading);

  const { isFetched: isLoaded } = useCustomPrimaryLoading();
  const hasChosenPlan = useAuthStore((state) => state.has_chosen_plan);
  const isLoadingUser = useAuthStore((state) => state.isLoadingUser);
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  const navigate = useNavigate();

  const { isFetched } = useGetAutoLogin({ enabled: isLoaded });
  useGetVersionQuery({ enabled: isFetched });
  useGetConfig({ enabled: isFetched });
  const { isFetched: typesLoaded } = useGetTypes({ enabled: isFetched });
  useGetGlobalVariables({ enabled: typesLoaded });
  useGetTagsQuery({ enabled: typesLoaded });
  useGetFoldersQuery({
    enabled: typesLoaded,
  });
  const { isFetched: isExamplesFetched } = useGetBasicExamplesQuery({
    enabled: typesLoaded,
  });

  useEffect(() => {
    if (isFetched) {
      refreshStars();
    }
  }, [isFetched]);

  useEffect(() => {
    if (!dark) {
      document.getElementById("body")!.classList.remove("dark");
    } else {
      document.getElementById("body")!.classList.add("dark");
    }
  }, [dark]);

  useEffect(() => {
    if (isAuthenticated && !isLoadingUser) {
      if (!hasChosenPlan && location.pathname !== '/billing/plans') {
        navigate("/billing/plans", { replace: true });
      }
    }
  }, [isAuthenticated, isLoadingUser, hasChosenPlan, navigate, location.pathname]);

  const showLoading = isLoading || !isFetched || !isExamplesFetched || !typesLoaded || (isAuthenticated && isLoadingUser);

  return (
    //need parent component with width and height
    <>
      {isLoaded ? (
        (isLoading || !isFetched || !isExamplesFetched || !typesLoaded) && (
          <LoadingPage overlay />
        )
      ) : (
        <CustomLoadingPage />
      )}
      {isFetched && isExamplesFetched && typesLoaded && <Outlet />}
    </>
  );
}
