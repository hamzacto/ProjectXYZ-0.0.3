import LangflowLogo from "@/assets/LangflowLogo.svg?react";
import InputComponent from "@/components/core/parameterRenderComponent/components/inputComponent";
import { ENABLE_NEW_LOGO } from "@/customization/feature-flags";
import { useCustomNavigate } from "@/customization/hooks/use-custom-navigate";
import * as Form from "@radix-ui/react-form";
import { FormEvent, useEffect, useState } from "react";
import { Button } from "../../components/ui/button";
import useAlertStore from "../../stores/alertStore";
import { api } from "../../controllers/API/api";
import { getURL } from "../../controllers/API/helpers/constants";

export default function ResetPassword(): JSX.Element {
  const [password, setPassword] = useState<string>("");
  const [confirmPassword, setConfirmPassword] = useState<string>("");
  const [token, setToken] = useState<string>("");
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string>("");
  const [success, setSuccess] = useState<boolean>(false);
  const navigate = useCustomNavigate();
  const setSuccessData = useAlertStore((state) => state.setSuccessData);
  const setErrorData = useAlertStore((state) => state.setErrorData);

  // Get token from URL
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const tokenParam = params.get("token");
    if (!tokenParam) {
      setError("Missing password reset token");
    } else {
      setToken(tokenParam);
    }
  }, []);

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault();

    if (password !== confirmPassword) {
      setError("Passwords do not match");
      return;
    }

    if (password.length < 8) {
      setError("Password must be at least 8 characters long");
      return;
    }

    if (!token) {
      setError("Missing password reset token");
      return;
    }

    setIsLoading(true);
    setError("");

    try {
      const response = await api.post(`${getURL("USERS")}/reset-password`, {
        token,
        new_password: password,
      });

      if (response.status === 200) {
        setSuccess(true);
      } else {
        setError("Failed to reset password");
      }
    } catch (err: any) {
      console.error("Password reset error:", err);
      // Check for social login error message
      if (err.response?.data?.detail?.includes("social login")) {
        setError("This account is connected with a social login provider (like Google). Please use your social login to access your account.");
      } else {
        const errorMessage = err.response?.data?.detail || "Failed to reset password. Please try again.";
        setError(errorMessage);
      }
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex h-screen w-full flex-col items-center justify-center bg-muted">
      <div className="flex w-96 flex-col items-center justify-center gap-4 rounded-lg bg-background p-8 shadow-lg">
        {ENABLE_NEW_LOGO ? (
          <LangflowLogo
            title="Langflow logo"
            className="mb-4 h-10 w-10 scale-[1.5]"
          />
        ) : (
          <span className="mb-4 text-5xl">⛓️</span>
        )}
        <h1 className="mb-4 text-2xl font-semibold text-primary">Reset Your Password</h1>

        {success ? (
          <div className="flex flex-col items-center gap-4">
            <div className="flex h-16 w-16 items-center justify-center rounded-full bg-green-100">
              <svg 
                className="h-8 w-8 text-green-600" 
                fill="none" 
                stroke="currentColor" 
                viewBox="0 0 24 24" 
                xmlns="http://www.w3.org/2000/svg"
              >
                <path 
                  strokeLinecap="round" 
                  strokeLinejoin="round" 
                  strokeWidth={2} 
                  d="M5 13l4 4L19 7" 
                />
              </svg>
            </div>
            <p className="text-center text-lg">Password reset successful!</p>
            <p className="text-center text-sm text-muted-foreground">
              You can now log in with your new password.
            </p>
            <Button 
              className="mt-2 w-full" 
              onClick={() => navigate("/login")}
            >
              Go to Login
            </Button>
          </div>
        ) : (
          <Form.Root
            onSubmit={handleSubmit}
            className="w-full"
          >
            {error && (
              <div className="mb-4 rounded-md bg-red-50 p-3 text-sm text-red-500">
                {error}
              </div>
            )}

            <div className="mb-4 w-full">
              <Form.Field name="password">
                <Form.Label className="data-[invalid]:label-invalid">
                  New Password <span className="font-medium text-destructive">*</span>
                </Form.Label>
                <InputComponent
                  onChange={(value) => setPassword(value)}
                  value={password}
                  isForm
                  password={true}
                  required
                  placeholder="New password"
                  className="w-full"
                />
                <Form.Message className="field-invalid" match="valueMissing">
                  Please enter a password
                </Form.Message>
              </Form.Field>
            </div>

            <div className="mb-6 w-full">
              <Form.Field 
                name="confirmPassword"
                serverInvalid={password !== confirmPassword}
              >
                <Form.Label className="data-[invalid]:label-invalid">
                  Confirm New Password <span className="font-medium text-destructive">*</span>
                </Form.Label>
                <InputComponent
                  onChange={(value) => setConfirmPassword(value)}
                  value={confirmPassword}
                  isForm
                  password={true}
                  required
                  placeholder="Confirm new password"
                  className="w-full"
                />
                <Form.Message className="field-invalid" match="valueMissing">
                  Please confirm your password
                </Form.Message>
                {password !== confirmPassword && (
                  <Form.Message className="field-invalid">
                    Passwords do not match
                  </Form.Message>
                )}
              </Form.Field>
            </div>

            <div className="w-full">
              <Form.Submit asChild>
                <Button
                  disabled={isLoading || !token || password.length < 8 || password !== confirmPassword}
                  type="submit"
                  className="w-full"
                >
                  {isLoading ? "Resetting..." : "Reset Password"}
                </Button>
              </Form.Submit>
            </div>
            
            <div className="mt-4 w-full text-center">
              <Button 
                variant="ghost" 
                className="w-full text-sm" 
                onClick={() => navigate("/login")}
              >
                Back to Login
              </Button>
            </div>
          </Form.Root>
        )}
      </div>
    </div>
  );
} 