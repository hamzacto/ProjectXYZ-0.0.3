import LangflowLogo from "@/assets/LangflowLogo.svg?react";
import InputComponent from "@/components/core/parameterRenderComponent/components/inputComponent";
import { useAddUser } from "@/controllers/API/queries/auth";
import { CustomLink } from "@/customization/components/custom-link";
import { ENABLE_NEW_LOGO } from "@/customization/feature-flags";
import { useCustomNavigate } from "@/customization/hooks/use-custom-navigate";
import { track } from "@/customization/utils/analytics";
import * as Form from "@radix-ui/react-form";
import { FormEvent, useContext, useEffect, useState } from "react";
import { Button } from "../../components/ui/button";
import { Input } from "../../components/ui/input";
import { SIGNUP_ERROR_ALERT } from "../../constants/alerts_constants";
import {
  CONTROL_INPUT_STATE,
  SIGN_UP_SUCCESS,
} from "../../constants/constants";
import { AuthContext } from "../../contexts/authContext";
import useAlertStore from "../../stores/alertStore";
import {
  UserInputType,
  inputHandlerEventType,
  signUpInputStateType,
} from "../../types/components";

export default function SignUp(): JSX.Element {
  const [inputState, setInputState] =
    useState<signUpInputStateType>(CONTROL_INPUT_STATE);

  const [isDisabled, setDisableBtn] = useState<boolean>(true);

  const { password, cnfPassword, username, email } = inputState;
  const setSuccessData = useAlertStore((state) => state.setSuccessData);
  const setErrorData = useAlertStore((state) => state.setErrorData);
  const navigate = useCustomNavigate();
  const { login, getUser } = useContext(AuthContext);

  const { mutate: mutateAddUser } = useAddUser();

  function handleInput({
    target: { name, value },
  }: inputHandlerEventType): void {
    setInputState((prev) => ({ ...prev, [name]: value }));
  }

  // Validate email format
  function isValidEmail(email: string): boolean {
    const regex = /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/;
    return regex.test(email);
  }

  // Validate password strength
  function isStrongPassword(password: string): { valid: boolean; errors: string[] } {
    const errors: string[] = [];
    
    if (password.length < 8) {
      errors.push("Password must be at least 8 characters long");
    }
    
    if (!/[A-Z]/.test(password)) {
      errors.push("Password must contain at least one uppercase letter");
    }
    
    if (!/[a-z]/.test(password)) {
      errors.push("Password must contain at least one lowercase letter");
    }
    
    if (!/[0-9]/.test(password)) {
      errors.push("Password must contain at least one number");
    }
    
    if (!/[^A-Za-z0-9]/.test(password)) {
      errors.push("Password must contain at least one special character");
    }
    
    return {
      valid: errors.length === 0,
      errors
    };
  }

  function signUpWithGoogle() {
    // Redirect the current window to the Google OAuth endpoint
    window.location.href = "/api/v1/login/google";
  }

  const [passwordTouched, setPasswordTouched] = useState(false);
  const passwordValidation = isStrongPassword(password);

  // Reverse order: Show password requirements first, then check for matching
  const shouldShowPasswordRequirements = passwordTouched && password !== "";
  // Only show password match error if requirements are met and passwords don't match
  const shouldShowMatchError = passwordValidation.valid && password !== cnfPassword && password !== "" && cnfPassword !== "";

  useEffect(() => {
    if (password !== cnfPassword) return setDisableBtn(true);
    if (password === "" || cnfPassword === "") return setDisableBtn(true);
    if (username === "") return setDisableBtn(true);
    if (email === "" || !isValidEmail(email)) return setDisableBtn(true);
    if (!passwordValidation.valid) return setDisableBtn(true);
    setDisableBtn(false);
  }, [password, cnfPassword, username, email, handleInput]);

  // Set up message listener for Google OAuth popup
  useEffect(() => {
    // Check for auth errors in sessionStorage (set by Google OAuth callback)
    const authError = sessionStorage.getItem('auth_error');
    if (authError) {
      // Display the error
      setErrorData({
        title: SIGNUP_ERROR_ALERT,
        list: [authError],
      });
      // Remove the error from sessionStorage
      sessionStorage.removeItem('auth_error');
    }
  }, [setErrorData]);

  function handleSignup(): void {
    const { username, password, email } = inputState;
    const newUser: UserInputType = {
      username: username.trim(),
      password: password.trim(),
      email: email.trim(),
    };

    mutateAddUser(newUser, {
      onSuccess: (user) => {
        track("User Signed Up", user);
        setSuccessData({
          title: SIGN_UP_SUCCESS,
        });
        navigate("/login");
      },
      onError: (error) => {
        const {
          response: {
            data: { detail },
          },
        } = error;
        setErrorData({
          title: SIGNUP_ERROR_ALERT,
          list: [detail],
        });
      },
    });
  }

  return (
    <Form.Root
      onSubmit={(event: FormEvent<HTMLFormElement>) => {
        if (password === "") {
          event.preventDefault();
          return;
        }

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
            Sign up for Langflow
          </span>
          <div className="mb-3 w-full">
            <Form.Field name="username">
              <Form.Label className="data-[invalid]:label-invalid">
                Username <span className="font-medium text-destructive">*</span>
              </Form.Label>

              <Form.Control asChild>
                <Input
                  type="username"
                  onChange={({ target: { value } }) => {
                    handleInput({ target: { name: "username", value } });
                  }}
                  value={username}
                  className="w-full"
                  required
                  placeholder="Username"
                />
              </Form.Control>

              <Form.Message match="valueMissing" className="field-invalid">
                Please enter your username
              </Form.Message>
            </Form.Field>
          </div>
          <div className="mb-3 w-full">
            <Form.Field name="email">
              <Form.Label className="data-[invalid]:label-invalid">
                Email <span className="font-medium text-destructive">*</span>
              </Form.Label>

              <Form.Control asChild>
                <Input
                  type="email"
                  onChange={({ target: { value } }) => {
                    handleInput({ target: { name: "email", value } });
                  }}
                  value={email}
                  className="w-full"
                  required
                  placeholder="Email address"
                />
              </Form.Control>

              <Form.Message match="valueMissing" className="field-invalid">
                Please enter your email
              </Form.Message>
              {email !== "" && !isValidEmail(email) && (
                <div className="field-invalid">
                  Please enter a valid email address
                </div>
              )}
            </Form.Field>
          </div>
          <div className="mb-3 w-full">
            <Form.Field name="password" serverInvalid={password != cnfPassword}>
              <Form.Label className="data-[invalid]:label-invalid">
                Password <span className="font-medium text-destructive">*</span>
              </Form.Label>
              <InputComponent
                onChange={(value) => {
                  handleInput({ target: { name: "password", value } });
                  setPasswordTouched(true);
                }}
                value={password}
                isForm
                password={true}
                required
                placeholder="Password"
                className="w-full"
              />

              <Form.Message className="field-invalid" match="valueMissing">
                Please enter a password
              </Form.Message>

              {/* Password requirements with smooth transition */}
              <div 
                className={`text-xs overflow-hidden transition-all duration-300 ease-in-out ${
                  shouldShowPasswordRequirements && !passwordValidation.valid 
                    ? "mt-2 max-h-60 opacity-100" 
                    : "max-h-0 opacity-0 mt-0"
                }`}
              >
                <p className="mb-1 text-destructive">Password must:</p>
                <ul className="list-disc pl-5 space-y-1">
                  {passwordValidation.errors.map((error, index) => (
                    <li key={index} className="text-destructive">
                      {error.replace("Password must ", "")}
                    </li>
                  ))}
                </ul>
              </div>
              
              {/* Password matching error - only show this when requirements are met but passwords don't match */}
              {shouldShowMatchError && (
                <Form.Message className="field-invalid">
                  Passwords do not match
                </Form.Message>
              )}
            </Form.Field>
          </div>
          <div className="w-full">
            <Form.Field
              name="confirmpassword"
              serverInvalid={password != cnfPassword}
            >
              <Form.Label className="data-[invalid]:label-invalid">
                Confirm your password{" "}
                <span className="font-medium text-destructive">*</span>
              </Form.Label>

              <InputComponent
                onChange={(value) => {
                  handleInput({ target: { name: "cnfPassword", value } });
                }}
                value={cnfPassword}
                isForm
                password={true}
                required
                placeholder="Confirm your password"
                className="w-full"
              />

              <Form.Message className="field-invalid" match="valueMissing">
                Please confirm your password
              </Form.Message>
            </Form.Field>
          </div>
          <div className="w-full">
            <Form.Submit asChild>
              <Button
                type="submit"
                className="mb-3 w-full"
                disabled={isDisabled}
                onClick={() => {
                  handleSignup();
                }}
              >
                Sign Up
              </Button>
            </Form.Submit>
          </div>
          
          <div className="flex items-center mb-3 w-full">
            <div className="flex-grow h-px bg-gray-300"></div>
            <span className="px-2 text-sm text-gray-500">OR</span>
            <div className="flex-grow h-px bg-gray-300"></div>
          </div>
          
          <Button 
            type="button" 
            variant="outline" 
            className="w-full flex items-center justify-center gap-2 mb-3"
            onClick={signUpWithGoogle}
          >
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48" width="24px" height="24px">
              <path fill="#FFC107" d="M43.611,20.083H42V20H24v8h11.303c-1.649,4.657-6.08,8-11.303,8c-6.627,0-12-5.373-12-12c0-6.627,5.373-12,12-12c3.059,0,5.842,1.154,7.961,3.039l5.657-5.657C34.046,6.053,29.268,4,24,4C12.955,4,4,12.955,4,24c0,11.045,8.955,20,20,20c11.045,0,20-8.955,20-20C44,22.659,43.862,21.35,43.611,20.083z" />
              <path fill="#FF3D00" d="M6.306,14.691l6.571,4.819C14.655,15.108,18.961,12,24,12c3.059,0,5.842,1.154,7.961,3.039l5.657-5.657C34.046,6.053,29.268,4,24,4C16.318,4,9.656,8.337,6.306,14.691z" />
              <path fill="#4CAF50" d="M24,44c5.166,0,9.86-1.977,13.409-5.192l-6.19-5.238C29.211,35.091,26.715,36,24,36c-5.202,0-9.619-3.317-11.283-7.946l-6.522,5.025C9.505,39.556,16.227,44,24,44z" />
              <path fill="#1976D2" d="M43.611,20.083H42V20H24v8h11.303c-0.792,2.237-2.231,4.166-4.087,5.571c0.001-0.001,0.002-0.001,0.003-0.002l6.19,5.238C36.971,39.205,44,34,44,24C44,22.659,43.862,21.35,43.611,20.083z" />
            </svg>
            Sign up with Google
          </Button>

          <div className="w-full">
            <CustomLink to="/login">
              <Button className="w-full" variant="outline">
                Already have an account?&nbsp;<b>Sign in</b>
              </Button>
            </CustomLink>
          </div>
        </div>
      </div>
    </Form.Root>
  );
}
