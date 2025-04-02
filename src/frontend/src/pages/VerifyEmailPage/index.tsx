import LangflowLogo from "@/assets/LangflowLogo.svg?react";
import { ENABLE_NEW_LOGO } from "@/customization/feature-flags";
import { useCustomNavigate } from "@/customization/hooks/use-custom-navigate";
import { useEffect, useState } from "react";
import { Button } from "../../components/ui/button";
import useAlertStore from "../../stores/alertStore";

export default function VerifyEmail(): JSX.Element {
  const [verifying, setVerifying] = useState<boolean>(true);
  const [success, setSuccess] = useState<boolean>(false);
  const [error, setError] = useState<string>("");
  const navigate = useCustomNavigate();
  const setErrorData = useAlertStore((state) => state.setErrorData);

  useEffect(() => {
    const verifyToken = async () => {
      try {
        // Get token from URL parameters
        const params = new URLSearchParams(window.location.search);
        const token = params.get("token");

        if (!token) {
          setError("Missing verification token");
          setVerifying(false);
          return;
        }

        // Make a direct fetch call to bypass authentication interceptors
        // Using fetch instead of axios to avoid authentication interceptors
        const backendUrl = window.location.origin;
        const response = await fetch(`${backendUrl}/api/v1/users/verify?token=${token}`);
        const data = await response.json();
        
        if (response.ok) {
          setSuccess(true);
        } else {
          const errorMessage = data?.detail || "Failed to verify email. The token may be invalid or expired.";
          setError(errorMessage);
        }
      } catch (err: any) {
        console.error("Verification error:", err);
        
        let errorMessage = "Failed to verify email. Please try again.";
        if (err.message) {
          errorMessage = err.message;
        }
        setError(errorMessage);
      } finally {
        setVerifying(false);
      }
    };

    verifyToken();
  }, []);

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
        <h1 className="mb-4 text-2xl font-semibold text-primary">Email Verification</h1>

        {verifying && (
          <div className="flex flex-col items-center gap-2">
            <div className="h-12 w-12 animate-spin rounded-full border-b-2 border-primary"></div>
            <p className="text-center text-lg">Verifying your email...</p>
          </div>
        )}

        {!verifying && success && (
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
            <p className="text-center text-lg">Your email has been successfully verified!</p>
            <p className="text-center text-sm text-muted-foreground">
              You can now log in to your account.
            </p>
            <Button 
              className="mt-2 w-full" 
              onClick={() => navigate("/login")}
            >
              Go to Login
            </Button>
          </div>
        )}

        {!verifying && !success && (
          <div className="flex flex-col items-center gap-4">
            <div className="flex h-16 w-16 items-center justify-center rounded-full bg-red-100">
              <svg 
                className="h-8 w-8 text-red-600" 
                fill="none" 
                stroke="currentColor" 
                viewBox="0 0 24 24" 
                xmlns="http://www.w3.org/2000/svg"
              >
                <path 
                  strokeLinecap="round" 
                  strokeLinejoin="round" 
                  strokeWidth={2} 
                  d="M6 18L18 6M6 6l12 12" 
                />
              </svg>
            </div>
            <p className="text-center text-lg">Verification Failed</p>
            <p className="text-center text-sm text-destructive">
              {error}
            </p>
            <div className="flex w-full flex-col gap-2">
              <Button 
                className="w-full" 
                onClick={() => navigate("/signup")}
              >
                Sign Up Again
              </Button>
              <Button 
                variant="outline"
                className="w-full" 
                onClick={() => navigate("/login")}
              >
                Back to Login
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
} 