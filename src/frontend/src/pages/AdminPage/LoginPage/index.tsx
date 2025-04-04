import LangflowLogo from "@/assets/LangflowLogo.svg?react";
import { useLoginUser } from "@/controllers/API/queries/auth";
import { ENABLE_NEW_LOGO } from "@/customization/feature-flags";
import { useContext, useState, useEffect } from "react";
import { Button } from "../../../components/ui/button";
import { Input } from "../../../components/ui/input";
import { SIGNIN_ERROR_ALERT } from "../../../constants/alerts_constants";
import { CONTROL_LOGIN_STATE } from "../../../constants/constants";
import { AuthContext } from "../../../contexts/authContext";
import useAlertStore from "../../../stores/alertStore";
import { LoginType } from "../../../types/api";
import {
  inputHandlerEventType,
  loginInputStateType,
} from "../../../types/components";

export default function LoginAdminPage() {
  const [inputState, setInputState] =
    useState<loginInputStateType>(CONTROL_LOGIN_STATE);
  const { login, getUser } = useContext(AuthContext);

  const { password, username } = inputState;
  const setErrorData = useAlertStore((state) => state.setErrorData);
  function handleInput({
    target: { name, value },
  }: inputHandlerEventType): void {
    setInputState((prev) => ({ ...prev, [name]: value }));
  }

  const { mutate } = useLoginUser();

  function signIn() {
    const user: LoginType = {
      username: username,
      password: password,
    };

    mutate(user, {
      onSuccess: (res) => {
        login(res.access_token, "login", res.refresh_token);
      },
      onError: (error) => {
        setErrorData({
          title: SIGNIN_ERROR_ALERT,
          list: [error["response"]["data"]["detail"]],
        });
      },
    });
  }

  function signInWithGoogle() {
    // Open a popup window for the Google OAuth flow
    const width = 500;
    const height = 600;
    const left = window.screenX + (window.outerWidth - width) / 2;
    const top = window.screenY + (window.outerHeight - height) / 2;
    
    const popup = window.open(
      "/api/v1/login/google",
      "google-login",
      `width=${width},height=${height},left=${left},top=${top}`
    );
    
    // Handle messages from the popup
    const handleMessage = (event: MessageEvent) => {
      if (event.data.googleLoginSuccess) {
        // Close the popup and refresh the page to apply the new session
        if (popup) popup.close();
        window.location.href = "/admin";
      }
      if (event.data.googleLoginError) {
        if (popup) popup.close();
        setErrorData({
          title: SIGNIN_ERROR_ALERT,
          list: ["Google login failed. Please try again."],
        });
      }
    };
    
    window.addEventListener("message", handleMessage);
    
    // Clean up the event listener when component unmounts
    return () => {
      window.removeEventListener("message", handleMessage);
    };
  }

  useEffect(() => {
    // Set up message listener for Google OAuth popup
    const handleMessage = (event: MessageEvent) => {
      if (event.data.googleLoginSuccess) {
        // If we received tokens directly from the popup
        if (event.data.access_token && event.data.refresh_token) {
          // Directly use the tokens to log in
          login(event.data.access_token, "google", event.data.refresh_token);
          // Call getUser explicitly to fetch user data
          setTimeout(() => {
            getUser();
            // Navigate after user data is loaded
            setTimeout(() => {
              window.location.href = "/admin";
            }, 100);
          }, 100);
        } else {
          // Fallback to reload if tokens weren't provided
          window.location.href = "/admin";
        }
      }
      if (event.data.googleLoginError) {
        setErrorData({
          title: SIGNIN_ERROR_ALERT,
          list: ["Google login failed. Please try again."],
        });
      }
    };
    
    window.addEventListener("message", handleMessage);
    
    // Clean up
    return () => {
      window.removeEventListener("message", handleMessage);
    };
  }, [setErrorData, login, getUser]);

  return (
    <div className="flex h-full w-full flex-col items-center justify-center bg-muted">
      <div className="flex w-72 flex-col items-center justify-center gap-2">
        {ENABLE_NEW_LOGO ? (
          <LangflowLogo
            title="Langflow logo"
            className="h-10 w-10 scale-[1.5]"
          />
        ) : (
          <span className="mb-4 text-5xl">⛓️</span>
        )}
        <span className="mb-6 text-2xl font-semibold text-primary">Admin</span>
        <Input
          onChange={({ target: { value } }) => {
            handleInput({ target: { name: "username", value } });
          }}
          className="bg-background"
          placeholder="Username or Email"
        />
        <Input
          type="password"
          onChange={({ target: { value } }) => {
            handleInput({ target: { name: "password", value } });
          }}
          className="bg-background"
          placeholder="Password"
        />
        <Button
          onClick={() => {
            signIn();
          }}
          variant="default"
          className="w-full"
        >
          Login
        </Button>
        
        <div className="flex items-center my-3 w-full">
          <div className="flex-grow h-px bg-gray-300"></div>
          <span className="px-2 text-sm text-gray-500">OR</span>
          <div className="flex-grow h-px bg-gray-300"></div>
        </div>
        
        <Button 
          onClick={signInWithGoogle}
          variant="outline" 
          className="w-full flex items-center justify-center gap-2"
        >
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48" width="24px" height="24px">
            <path fill="#FFC107" d="M43.611,20.083H42V20H24v8h11.303c-1.649,4.657-6.08,8-11.303,8c-6.627,0-12-5.373-12-12c0-6.627,5.373-12,12-12c3.059,0,5.842,1.154,7.961,3.039l5.657-5.657C34.046,6.053,29.268,4,24,4C12.955,4,4,12.955,4,24c0,11.045,8.955,20,20,20c11.045,0,20-8.955,20-20C44,22.659,43.862,21.35,43.611,20.083z" />
            <path fill="#FF3D00" d="M6.306,14.691l6.571,4.819C14.655,15.108,18.961,12,24,12c3.059,0,5.842,1.154,7.961,3.039l5.657-5.657C34.046,6.053,29.268,4,24,4C16.318,4,9.656,8.337,6.306,14.691z" />
            <path fill="#4CAF50" d="M24,44c5.166,0,9.86-1.977,13.409-5.192l-6.19-5.238C29.211,35.091,26.715,36,24,36c-5.202,0-9.619-3.317-11.283-7.946l-6.522,5.025C9.505,39.556,16.227,44,24,44z" />
            <path fill="#1976D2" d="M43.611,20.083H42V20H24v8h11.303c-0.792,2.237-2.231,4.166-4.087,5.571c0.001-0.001,0.002-0.001,0.003-0.002l6.19,5.238C36.971,39.205,44,34,44,24C44,22.659,43.862,21.35,43.611,20.083z" />
          </svg>
          Sign in with Google
        </Button>
      </div>
    </div>
  );
}
