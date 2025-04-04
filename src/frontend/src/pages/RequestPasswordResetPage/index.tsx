import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import * as Form from "@radix-ui/react-form";
import { Input } from "@/components/ui/input";
import LangflowLogo from "@/assets/LangflowLogo.svg?react";
import { ENABLE_NEW_LOGO } from "@/customization/feature-flags";
import { api } from "@/controllers/API/api";
import { getURL } from "@/controllers/API/helpers/constants";
import useAlertStore from "@/stores/alertStore";

const RequestPasswordResetPage: React.FC = () => {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [success, setSuccess] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const setErrorData = useAlertStore((state) => state.setErrorData);

  const isValidEmail = (email: string): boolean => {
    const regex = /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/;
    return regex.test(email);
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    
    if (!email || !isValidEmail(email)) {
      return;
    }

    setIsLoading(true);

    try {
      const response = await api.post(`${getURL("USERS")}/password-reset-request`, {
        email: email.trim(),
      });

      if (response.status === 200) {
        setSuccess(true);
      }
    } catch (err) {
      // Even if there's an error, we show success to prevent email enumeration
      console.error("Password reset error:", err);
      setSuccess(true);
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
        <h1 className="mb-4 text-2xl font-semibold text-primary">Reset Password</h1>

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
            <p className="text-center text-lg">Password Reset Email Sent</p>
            <p className="text-center text-sm text-muted-foreground">
              If an account exists with that email, we've sent instructions to reset your password.
            </p>
            <Button 
              className="mt-2 w-full" 
              onClick={() => navigate("/login")}
            >
              Back to Login
            </Button>
          </div>
        ) : (
          <Form.Root
            onSubmit={handleSubmit}
            className="w-full"
          >
            <p className="mb-4 text-sm text-muted-foreground">
              Enter your email address and we'll send you instructions to reset your password.
            </p>
            
            <p className="mb-4 text-sm text-muted-foreground">
              <strong>Note:</strong> If you signed up with Google, please use the Google login option instead of password reset.
            </p>

            <div className="mb-6 w-full">
              <Form.Field name="email">
                <Form.Label className="data-[invalid]:label-invalid">
                  Email Address <span className="font-medium text-destructive">*</span>
                </Form.Label>

                <Form.Control asChild>
                  <Input
                    type="email"
                    onChange={(e) => setEmail(e.target.value)}
                    value={email}
                    className="w-full"
                    required
                    placeholder="your-email@example.com"
                  />
                </Form.Control>

                <Form.Message match="valueMissing" className="field-invalid">
                  Please enter your email address
                </Form.Message>
                {email !== "" && !isValidEmail(email) && (
                  <div className="field-invalid">
                    Please enter a valid email address
                  </div>
                )}
              </Form.Field>
            </div>

            <div className="w-full">
              <Form.Submit asChild>
                <Button
                  disabled={isLoading || !email || !isValidEmail(email)}
                  type="submit"
                  className="w-full"
                >
                  {isLoading ? "Sending..." : "Send Reset Link"}
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
};

export default RequestPasswordResetPage; 