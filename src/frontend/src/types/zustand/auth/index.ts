import { Users } from "@/types/api";

export interface AuthStoreType {
  isAdmin: boolean;
  isAuthenticated: boolean;
  accessToken: string | null;
  userData: Users | null;
  autoLogin: boolean | null;
  apiKey: string | null;
  authenticationErrorCount: number;
  has_chosen_plan: boolean;
  isLoadingUser: boolean;

  setIsAdmin: (isAdmin: boolean) => void;
  setIsAuthenticated: (isAuthenticated: boolean) => void;
  setAccessToken: (accessToken: string | null) => void;
  setUserData: (userData: Users | null) => void;
  setAutoLogin: (autoLogin: boolean) => void;
  setApiKey: (apiKey: string | null) => void;
  setAuthenticationErrorCount: (authenticationErrorCount: number) => void;
  setHasChosenPlan: (has_chosen_plan: boolean) => void;
  setIsLoadingUser: (isLoadingUser: boolean) => void;
  logout: () => Promise<void>;
  // setUserData: (userData: Users | null) => void;
  // setIsAdmin: (isAdmin: boolean) => void;
  // setApiKey: (apiKey: string | null) => void;

  // getUser: () => void;
  // login: (newAccessToken: string) => void;
  // storeApiKey: (apikey: string) => void;
}
