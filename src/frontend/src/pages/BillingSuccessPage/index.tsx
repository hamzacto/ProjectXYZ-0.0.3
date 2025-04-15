import { useState, useEffect } from "react";
import LangflowLogo from "@/assets/LangflowLogo.svg?react";
import { ENABLE_NEW_LOGO } from "@/customization/feature-flags";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { useCustomNavigate } from "@/customization/hooks/use-custom-navigate";
import { LANGFLOW_ACCESS_TOKEN } from "@/constants/constants";
import { Cookies } from "react-cookie";
import { Check, Info, CreditCard, Loader2 } from "lucide-react";
import { api } from "@/controllers/API/api";

// Define interface for subscription plans
interface SubscriptionPlan {
  id: string;
  name: string;
  description: string;
  monthly_quota_credits: number;
  max_flows: number;
  max_concurrent_flows: number;
}

export default function BillingSuccessPage(): JSX.Element {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [planInfo, setPlanInfo] = useState<SubscriptionPlan | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  
  const navigate = useCustomNavigate();
  const cookies = new Cookies();

  // Check if user is authenticated and get plan information
  useEffect(() => {
    const initializePage = async () => {
      try {
        const token = cookies.get(LANGFLOW_ACCESS_TOKEN);
        if (!token) {
          navigate("/login");
          return;
        }
        
        // Get session ID from URL query params
        const params = new URLSearchParams(window.location.search);
        const session = params.get('session_id');
        setSessionId(session);
        
        // Try to get subscription plan information
        await fetchPlanInfo();
        
      } catch (error) {
        console.error("Error initializing page:", error);
      }
    };
    
    initializePage();
  }, [navigate]);

  // Function to fetch plan information
  const fetchPlanInfo = async () => {
    setIsLoading(true);
    try {
      // First try to get available plans
      const plansResponse = await api.get('/api/v1/billing/subscription-plans');
      const plans = plansResponse.data;
      
      if (plans && plans.length > 0) {
        // Get the active plan - this is a simplification since we don't have a direct endpoint
        // In a real scenario, we'd match this with the user's subscribed plan ID
        
        // Try to get the selected plan from local storage if it was saved during checkout
        const selectedPlanId = localStorage.getItem('selected_plan_id');
        
        if (selectedPlanId) {
          const selectedPlan = plans.find(plan => plan.id === selectedPlanId);
          if (selectedPlan) {
            setPlanInfo(selectedPlan);
            
            // Store the current subscription plan ID for future reference
            // This will be used when checking if a user is changing plans
            localStorage.setItem('current_subscription_plan_id', selectedPlan.id);
            return;
          }
        }
        
        // If we can't find the selected plan, just show the first non-free plan
        const nonFreePlan = plans.find(plan => plan.price_monthly_usd > 0);
        if (nonFreePlan) {
          setPlanInfo(nonFreePlan);
          // Store the current subscription plan ID
          localStorage.setItem('current_subscription_plan_id', nonFreePlan.id);
        } else {
          // Default to the first plan if no paid plans are found
          setPlanInfo(plans[0]);
          // Store the current subscription plan ID
          localStorage.setItem('current_subscription_plan_id', plans[0].id);
        }
      }
    } catch (error) {
      console.error("Error fetching plan info:", error);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen w-full flex-col items-center justify-center bg-muted p-4">
      <div className="w-full max-w-2xl">
        <Card className="shadow-lg">
          <CardHeader className="text-center pb-2">
            {ENABLE_NEW_LOGO ? (
              <LangflowLogo
                title="Langflow logo"
                className="mx-auto mb-6 h-12 w-12"
              />
            ) : (
              <span className="mx-auto mb-6 text-5xl">⛓️</span>
            )}
            <div className="flex flex-col items-center justify-center">
              <div className="flex h-16 w-16 items-center justify-center rounded-full bg-green-100 mb-4">
                <Check className="h-8 w-8 text-green-600" />
              </div>
              <CardTitle className="text-2xl font-bold">Subscription Successful!</CardTitle>
              <CardDescription className="mt-2 text-center">
                Thank you for subscribing to Langflow. Your payment has been processed successfully.
                {sessionId && <div className="mt-1 text-xs">Reference: {sessionId.substring(0, 12)}...</div>}
              </CardDescription>
            </div>
          </CardHeader>
          
          <CardContent className="flex flex-col items-center pt-6">
            <div className="w-full space-y-6">
              {/* Plan Information */}
              {isLoading ? (
                <div className="flex justify-center py-4">
                  <Loader2 className="h-6 w-6 animate-spin text-primary" />
                </div>
              ) : planInfo ? (
                <div className="rounded-lg border bg-card p-4">
                  <h3 className="font-semibold text-lg mb-2 flex items-center gap-2">
                    <CreditCard className="h-5 w-5 text-primary" />
                    Your Subscription
                  </h3>
                  <div className="space-y-3">
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Plan</span>
                      <span className="font-medium">{planInfo.name}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Monthly Credits</span>
                      <span className="font-medium">{planInfo.monthly_quota_credits.toLocaleString()}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Max Flows</span>
                      <span className="font-medium">{planInfo.max_flows === 0 ? "Unlimited" : planInfo.max_flows}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Max Concurrent Flows</span>
                      <span className="font-medium">{planInfo.max_concurrent_flows}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-muted-foreground">Status</span>
                      <span className="font-medium text-green-600">Active</span>
                    </div>
                  </div>
                </div>
              ) : null}

              <div className="rounded-lg border bg-card p-4">
                <h3 className="font-semibold text-lg mb-2 flex items-center gap-2">
                  <Info className="h-5 w-5 text-primary" />
                  What's Next
                </h3>
                <p className="text-sm text-muted-foreground">
                  Your subscription is now active. You can now access all the features included in your subscription plan.
                  Your new limits and capabilities are available immediately. Visit your dashboard to start building flows
                  with your new subscription benefits.
                </p>
              </div>
            </div>
          </CardContent>
          
          <CardFooter className="flex flex-col sm:flex-row gap-3 pt-6">
            <Button 
              onClick={() => navigate("/flows")}
              className="w-full sm:w-auto"
            >
              Go to Dashboard
            </Button>
            <Button 
              variant="outline" 
              onClick={() => navigate("/settings/general")}
              className="w-full sm:w-auto"
            >
              Account Settings
            </Button>
          </CardFooter>
        </Card>
        
        <div className="mt-4 text-center text-sm text-muted-foreground">
          <p>
            Need help? <a href="mailto:support@langflow.ai" className="text-primary hover:underline">Contact Support</a>
          </p>
        </div>
      </div>
    </div>
  );
} 