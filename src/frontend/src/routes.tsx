import { lazy } from "react";
import {
  createBrowserRouter,
  createRoutesFromElements,
  Outlet,
  Route,
} from "react-router-dom";
import { ProtectedAdminRoute } from "./components/authorization/authAdminGuard";
import { ProtectedRoute } from "./components/authorization/authGuard";
import { ProtectedLoginRoute } from "./components/authorization/authLoginGuard";
import { AuthSettingsGuard } from "./components/authorization/authSettingsGuard";
import { StoreGuard } from "./components/authorization/storeGuard";
import ContextWrapper from "./contexts";
import { CustomNavigate } from "./customization/components/custom-navigate";
import { BASENAME } from "./customization/config-constants";
import {
  ENABLE_CUSTOM_PARAM,
  ENABLE_HOMEPAGE,
} from "./customization/feature-flags";
import { AppAuthenticatedPage } from "./pages/AppAuthenticatedPage";
import { AppInitPage } from "./pages/AppInitPage";
import { AppWrapperPage } from "./pages/AppWrapperPage";
import { DashboardWrapperPage } from "./pages/DashboardWrapperPage";
import FlowPage from "./pages/FlowPage";
import LoginPage from "./pages/LoginPage";
import MyCollectionComponent from "./pages/MainPage/oldComponents/myCollectionComponent";
import OldHomePage from "./pages/MainPage/oldPages/mainPage";
import CollectionPage from "./pages/MainPage/pages";
import HomePage from "./pages/MainPage/pages/homePage";
import SettingsPage from "./pages/SettingsPage";
import ApiKeysPage from "./pages/SettingsPage/pages/ApiKeysPage";
import GeneralPage from "./pages/SettingsPage/pages/GeneralPage";
import GlobalVariablesPage from "./pages/SettingsPage/pages/GlobalVariablesPage";
import MessagesPage from "./pages/SettingsPage/pages/messagesPage";
import ShortcutsPage from "./pages/SettingsPage/pages/ShortcutsPage";
import StoreApiKeyPage from "./pages/SettingsPage/pages/StoreApiKeyPage";
import StorePage from "./pages/StorePage";
import ViewPage from "./pages/ViewPage";
import VerifyEmailPage from "./pages/VerifyEmailPage";
import ResetPasswordPage from "./pages/ResetPasswordPage";
import RequestPasswordResetPage from "./pages/RequestPasswordResetPage";
import GuidedAgentIntegrations from "./modals/templatesModal/components/GuidedAgentIntegrations";
import GuidedAgentIntegrationsPage from "./pages/GuidedAgentIntegrationsPage";
import GmailIntegrationsDetailPage from "./pages/GmailIntegrationsDetailPage/index";
import SlackIntegrationsDetailPage from "./pages/SlackIntegrationsDetailPage/index";
import HubSpotIntegrationsDetailPage from "./pages/HubSpotIntegrationsDetailPage/index";
import ChatPage from "./pages/Chat_Page";
import CheckoutPage from "./pages/CheckoutPage";
import BillingSuccessPage from "./pages/BillingSuccessPage";

const AdminPage = lazy(() => import("./pages/AdminPage"));
const LoginAdminPage = lazy(() => import("./pages/AdminPage/LoginPage"));
const DeleteAccountPage = lazy(() => import("./pages/DeleteAccountPage"));

const PlaygroundPage = lazy(() => import("./pages/Playground"));

const SignUp = lazy(() => import("./pages/SignUpPage"));
const router = createBrowserRouter(
  createRoutesFromElements([
    <Route
      path={ENABLE_CUSTOM_PARAM ? "/:customParam?" : "/"}
      element={
        <ContextWrapper>
          <Outlet />
        </ContextWrapper>
      }
    >
      <Route path="" element={<AppInitPage />}>
        <Route path="" element={<AppWrapperPage />}>
          <Route
            path=""
            element={
              <ProtectedRoute>
                <Outlet />
              </ProtectedRoute>
            }
          >
            <Route path="" element={<AppAuthenticatedPage />}>
              <Route path="" element={<DashboardWrapperPage />}>
                <Route
                  path=""
                  element={
                    ENABLE_HOMEPAGE ? <CollectionPage /> : <OldHomePage />
                  }
                >
                  <Route
                    index
                    element={<CustomNavigate replace to={"flows"} />}
                  />
                  <Route
                    path="flows/"
                    element={
                      ENABLE_HOMEPAGE ? (
                        <HomePage key="flows" type="flows" />
                      ) : (
                        <MyCollectionComponent key="flows" type="flows" />
                      )
                    }
                  >
                    <Route
                      path="folder/:folderId"
                      element={
                        ENABLE_HOMEPAGE ? (
                          <HomePage key="flows" type="flows" />
                        ) : (
                          <MyCollectionComponent key="flows" type="flows" />
                        )
                      }
                    />
                  </Route>
                  <Route
                    path="components/"
                    element={
                      ENABLE_HOMEPAGE ? (
                        <HomePage key="components" type="components" />
                      ) : (
                        <MyCollectionComponent
                          key="components"
                          type="component"
                        />
                      )
                    }
                  >
                    <Route
                      path="folder/:folderId"
                      element={
                        ENABLE_HOMEPAGE ? (
                          <HomePage key="components" type="components" />
                        ) : (
                          <MyCollectionComponent
                            key="components"
                            type="component"
                          />
                        )
                      }
                    />
                  </Route>
                  <Route
                    path="all/"
                    element={
                      ENABLE_HOMEPAGE ? (
                        <HomePage key="flows" type="flows" />
                      ) : (
                        <MyCollectionComponent key="all" type="all" />
                      )
                    }
                  >
                    <Route
                      path="folder/:folderId"
                      element={
                        ENABLE_HOMEPAGE ? (
                          <HomePage key="flows" type="flows" />
                        ) : (
                          <MyCollectionComponent key="all" type="all" />
                        )
                      }
                    />
                  </Route>
                </Route>
                <Route path="settings" element={<SettingsPage />}>
                  <Route
                    index
                    element={<CustomNavigate replace to={"general"} />}
                  />
                  <Route
                    path="global-variables"
                    element={<GlobalVariablesPage />}
                  />
                  <Route path="api-keys" element={<ApiKeysPage />} />
                  <Route
                    path="general/:scrollId?"
                    element={
                      <AuthSettingsGuard>
                        <GeneralPage />
                      </AuthSettingsGuard>
                    }
                  />
                  <Route path="shortcuts" element={<ShortcutsPage />} />
                  <Route path="messages" element={<MessagesPage />} />
                  <Route path="store" element={<StoreApiKeyPage />} />
                </Route>
                <Route
                  path="store"
                  element={
                    <StoreGuard>
                      <StorePage />
                    </StoreGuard>
                  }
                />
                <Route
                  path="integrations"
                  element={
                    <GuidedAgentIntegrationsPage />
                  }
                />
                <Route
                  path="integrations/gmail"
                  element={<GmailIntegrationsDetailPage />}
                />
                <Route
                  path="integrations/slack"
                  element={<SlackIntegrationsDetailPage />}
                />
                <Route
                  path="integrations/hubspot"
                  element={<HubSpotIntegrationsDetailPage />}
                />
                <Route
                  path="store/:id/"
                  element={
                    <StoreGuard>
                      <StorePage />
                    </StoreGuard>
                  }
                />
                <Route path="account">
                  <Route path="delete" element={<DeleteAccountPage />}></Route>
                </Route>
                <Route
                  path="admin"
                  element={
                    <ProtectedAdminRoute>
                      <AdminPage />
                    </ProtectedAdminRoute>
                  }
                />
                <Route path="chat/:id/">
                  <Route path="" element={<PlaygroundPage />} />
                </Route>
                <Route path="billing">
                  <Route path="plans" element={<CheckoutPage />} />
                  <Route path="success" element={<BillingSuccessPage />} />
                  <Route path="cancel" element={<DashboardWrapperPage />} />
                </Route>
              </Route>
              <Route path="flow/:id/">
                <Route path="" element={<DashboardWrapperPage />}>
                  <Route path="folder/:folderId/" element={<FlowPage />} />
                  <Route path="" element={<FlowPage />} />
                </Route>
                <Route path="view" element={<ViewPage />} />
              </Route>
              <Route path="playground/:id/">
                <Route path="" element={<PlaygroundPage />} />
              </Route>
            </Route>
          </Route>
          <Route
            path="login"
            element={
              <ProtectedLoginRoute>
                <LoginPage />
              </ProtectedLoginRoute>
            }
          />
          <Route
            path="signup"
            element={
              <ProtectedLoginRoute>
                <SignUp />
              </ProtectedLoginRoute>
            }
          />
          <Route
            path="verify-email"
            element={<VerifyEmailPage />}
          />
          <Route
            path="reset-password"
            element={<ResetPasswordPage />}
          />
          <Route
            path="login/admin"
            element={
              <ProtectedLoginRoute>
                <LoginAdminPage />
              </ProtectedLoginRoute>
            }
          />
          <Route
            path="forgot-password"
            element={<RequestPasswordResetPage />}
          />
        </Route>
      </Route>
      <Route path="*" element={<CustomNavigate replace to="/" />} />
    </Route>,
  ]),
  { basename: BASENAME || undefined },
);

export default router;
