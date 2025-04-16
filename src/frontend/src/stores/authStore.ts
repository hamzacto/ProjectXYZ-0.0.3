// authStore.js
import { LANGFLOW_ACCESS_TOKEN } from "@/constants/constants";
import { AuthStoreType } from "@/types/zustand/auth";
import { Cookies } from "react-cookie";
import { create } from "zustand";

const cookies = new Cookies();
const useAuthStore = create<AuthStoreType>((set, get) => ({
  isAdmin: false,
  isAuthenticated: !!cookies.get(LANGFLOW_ACCESS_TOKEN),
  accessToken: cookies.get(LANGFLOW_ACCESS_TOKEN) ?? null,
  userData: null,
  autoLogin: null,
  apiKey: cookies.get("apikey_tkn_lflw"),
  authenticationErrorCount: 0,
  has_chosen_plan: false,
  isLoadingUser: true,

  setIsAdmin: (isAdmin) => set({ isAdmin }),
  setIsAuthenticated: (isAuthenticated) => set({ isAuthenticated }),
  setAccessToken: (accessToken) => set({ accessToken }),
  setUserData: (userData) => set({ userData }),
  setAutoLogin: (autoLogin) => set({ autoLogin }),
  setApiKey: (apiKey) => set({ apiKey }),
  setAuthenticationErrorCount: (authenticationErrorCount) =>
    set({ authenticationErrorCount }),
  setHasChosenPlan: (has_chosen_plan) => set({ has_chosen_plan }),
  setIsLoadingUser: (isLoadingUser) => set({ isLoadingUser }),

  logout: async () => {
    get().setIsAuthenticated(false);
    get().setIsAdmin(false);
    get().setHasChosenPlan(false);

    set({
      isAdmin: false,
      userData: null,
      accessToken: null,
      isAuthenticated: false,
      autoLogin: false,
      apiKey: null,
      has_chosen_plan: false,
    });
  },
}));

export default useAuthStore;
