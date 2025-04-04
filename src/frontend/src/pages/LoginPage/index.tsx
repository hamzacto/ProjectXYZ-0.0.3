import LangflowLogo from "@/assets/LangflowLogo.svg?react";
import { useLoginUser } from "@/controllers/API/queries/auth";
import { CustomLink } from "@/customization/components/custom-link";
import { ENABLE_NEW_LOGO } from "@/customization/feature-flags";
import * as Form from "@radix-ui/react-form";
import { useContext, useState, useEffect } from "react";
import InputComponent from "../../components/core/parameterRenderComponent/components/inputComponent";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { SIGNIN_ERROR_ALERT } from "../../constants/alerts_constants";
import { CONTROL_LOGIN_STATE } from "../../constants/constants";
import { AuthContext } from "../../contexts/authContext";
import useAlertStore from "../../stores/alertStore";
import { LoginType } from "../../types/api";
import {
  inputHandlerEventType,
  loginInputStateType,
} from "../../types/components";

export default function LoginPage(): JSX.Element {
  const [inputState, setInputState] =
    useState<loginInputStateType>(CONTROL_LOGIN_STATE);

  const { password, username } = inputState;
  const { login, getUser } = useContext(AuthContext);
  const setErrorData = useAlertStore((state) => state.setErrorData);

  function handleInput({
    target: { name, value },
  }: inputHandlerEventType): void {
    setInputState((prev) => ({ ...prev, [name]: value }));
  }

  const { mutate } = useLoginUser();

  function signIn() {
    const user: LoginType = {
      username: username.trim(),
      password: password.trim(),
    };

    mutate(user, {
      onSuccess: (data) => {
        login(data.access_token, "login", data.refresh_token);
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
    // Redirect the current window to the Google OAuth endpoint
    window.location.href = "/api/v1/login/google";
  }

  useEffect(() => {
    // Check for auth errors in sessionStorage (set by Google OAuth callback)
    const authError = sessionStorage.getItem('auth_error');
    if (authError) {
      // Display the error
      setErrorData({
        title: SIGNIN_ERROR_ALERT,
        list: [authError],
      });
      // Remove the error from sessionStorage
      sessionStorage.removeItem('auth_error');
    }

    // Check for Google auth errors on page load (after redirect)
    const queryParams = new URLSearchParams(window.location.search);
    if (queryParams.get('error') === 'google_auth_failed') {
      setErrorData({
        title: SIGNIN_ERROR_ALERT,
        list: ["Google login failed. Please try again."],
      });
      // Optional: Clean up the URL
      if (window.history.replaceState) {
         const cleanURL = window.location.protocol + "//" + window.location.host + window.location.pathname;
         window.history.replaceState({}, document.title, cleanURL);
      }
    }
  }, [setErrorData]);

  return (
    <Form.Root
      onSubmit={(event) => {
        if (password === "") {
          event.preventDefault();
          return;
        }
        signIn();
        const data = Object.fromEntries(new FormData(event.currentTarget));
        event.preventDefault();
      }}
      className="h-screen w-full"
    >
      <div className="flex h-full w-full flex-col items-center justify-center bg-muted">
        <div className="flex w-72 flex-col items-center justify-center gap-2">
          {ENABLE_NEW_LOGO ? (
            <LangflowLogo
              title="Langflow logo"
              className="mb-4 h-10 w-10 scale-[1.5]"
            />
          ) : (
            <span className="mb-4 text-5xl">⛓️</span>
          )}
          <span className="mb-6 text-2xl font-semibold text-primary">
            Sign in to Langflow
          </span>
          <div className="mb-3 w-full">
            <Form.Field name="username">
              <Form.Label className="data-[invalid]:label-invalid">
                Username or Email <span className="font-medium text-destructive">*</span>
              </Form.Label>

              <Form.Control asChild>
                <Input
                  type="text"
                  onChange={({ target: { value } }) => {
                    handleInput({ target: { name: "username", value } });
                  }}
                  value={username}
                  className="w-full"
                  required
                  placeholder="Username or Email"
                />
              </Form.Control>

              <Form.Message match="valueMissing" className="field-invalid">
                Please enter your username or email
              </Form.Message>
            </Form.Field>
          </div>
          <div className="mb-3 w-full">
            <Form.Field name="password">
              <Form.Label className="data-[invalid]:label-invalid">
                Password <span className="font-medium text-destructive">*</span>
              </Form.Label>

              <InputComponent
                onChange={(value) => {
                  handleInput({ target: { name: "password", value } });
                }}
                value={password}
                isForm
                password={true}
                required
                placeholder="Password"
                className="w-full"
              />

              <Form.Message className="field-invalid" match="valueMissing">
                Please enter your password
              </Form.Message>
            </Form.Field>
          </div>
          <div className="mb-2 w-full text-left">
            <a href="/forgot-password.html" className="text-xs text-primary hover:underline">
              Forgot password?
            </a>
          </div>
          <div className="w-full">
            <Form.Submit asChild>
              <Button className="mr-3 mt-3 w-full" type="submit">
                Sign in
              </Button>
            </Form.Submit>
          </div>
          <div className="w-full">
            <CustomLink to="/signup">
              <Button className="w-full" variant="outline" type="button">
                Don't have an account?&nbsp;<b>Sign Up</b>
              </Button>
            </CustomLink>
          </div>
          <div className="flex items-center mb-3 w-full">
            <div className="flex-grow h-px bg-gray-300"></div>
            <span className="px-2 text-sm text-gray-500">OR</span>
            <div className="flex-grow h-px bg-gray-300"></div>
          </div>
          <Button 
            type="button" 
            variant="outline" 
            className="w-full flex items-center justify-center gap-2"
            onClick={signInWithGoogle}
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
    </Form.Root>
  );
}
