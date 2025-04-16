import { useState, useEffect, useRef, useCallback } from "react";
import * as Form from "@radix-ui/react-form";
import LangflowLogo from "@/assets/LangflowLogo.svg?react";
import { ENABLE_NEW_LOGO } from "@/customization/feature-flags";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/utils/utils";
import { useCustomNavigate } from "@/customization/hooks/use-custom-navigate";
import useAlertStore from "@/stores/alertStore";
import { api } from "@/controllers/API/api";
import { Check, Loader2, ChevronLeft, ChevronRight, ForwardIcon } from "lucide-react";
import { LANGFLOW_ACCESS_TOKEN } from "@/constants/constants";
import { Cookies } from "react-cookie";
import ConfirmationModal from "@/modals/confirmationModal";
import ForwardedIconComponent from "@/components/common/genericIconComponent";
import { useConfirmPlanSelection } from "@/controllers/API/queries/users/use-post-confirm-plan";
import useAuthStore from "@/stores/authStore";

// CSS for the animated gradient badge
const animatedGradientBadgeStyle = `
.animated-gradient-badge, .smb-animated-gradient-badge {
  background-size: 200% 200%;
  animation: gradientAnimation 13s ease infinite;
  /* Default: Light mode gradient */
  background-image: linear-gradient(45deg, 
    hsl(var(--primary)) 0%, 
    hsl(var(--primary) / 0.8) 25%, 
    hsl(265 89% 78% / 1) 50%, 
    hsl(var(--primary) / 0.8) 75%, 
    hsl(var(--primary)) 100%
  );
}

/* Dark mode - darker gradient using different color stops */
.dark .animated-gradient-badge, .dark .smb-animated-gradient-badge {
  background-image: linear-gradient(45deg, 
    hsl(var(--primary) / 0.6) 0%, 
    hsl(260 60% 45% / 1) 25%,  /* Darker Violet */
    hsl(250 50% 35% / 1) 50%,  /* Dark Indigo */
    hsl(260 60% 45% / 1) 75%,  /* Darker Violet */
    hsl(var(--primary) / 0.6) 100%
  );
}

/* SMB animated badge - blue theme - only color changes, animation is shared */
.smb-animated-gradient-badge {
  /* Default: Light mode gradient */
  background-image: linear-gradient(45deg, 
    #2563eb 0%,     /* Blue-700 */
    #3b82f6 25%,    /* Blue-500 */
    #60a5fa 50%,    /* Blue-400 */
    #3b82f6 75%,    /* Blue-500 */
    #2563eb 100%    /* Blue-700 */
  );
}

/* Dark mode - darker blue gradient */
.dark .smb-animated-gradient-badge {
  background-image: linear-gradient(45deg, 
    #1e40af 0%,     /* Darker Blue-800 */
    #2563eb 25%,    /* Blue-700 */
    #3b82f6 50%,    /* Blue-500 */
    #2563eb 75%,    /* Blue-700 */
    #1e40af 100%    /* Darker Blue-800 */
  );
}

/* Gradient glow borders for paid plan cards */
.card-lite-border {
  border: 2px solid transparent;
  background-origin: border-box;
  background-clip: padding-box, border-box;
  background-image: 
    linear-gradient(to bottom, hsl(var(--card)), hsl(var(--card))), 
    linear-gradient(45deg, #38b48b, #7ac7a6);
  box-shadow: 0 0 15px rgba(56, 180, 139, 0.4);
}

.card-pro-border {
  border: 2px solid transparent;
  background-origin: border-box;
  background-clip: padding-box, border-box;
  background-image: 
    linear-gradient(to bottom, hsl(var(--card)), hsl(var(--card))), 
    linear-gradient(45deg, #6866ef, #b66dd0);
  box-shadow: 0 0 15px rgba(104, 102, 239, 0.4);
}

.card-pro-plus-border {
  border: 2px solid transparent;
  background-origin: border-box;
  background-clip: padding-box, border-box;
  background-image: 
    linear-gradient(to bottom, hsl(var(--card)), hsl(var(--card))), 
    linear-gradient(45deg, #b66dd0, #f472b6);
  box-shadow: 0 0 15px rgba(182, 109, 208, 0.4);
}

.card-team-border {
  border: 2px solid transparent;
  background-origin: border-box;
  background-clip: padding-box, border-box;
  background-image: 
    linear-gradient(to bottom, hsl(var(--card)), hsl(var(--card))), 
    linear-gradient(45deg, #121055, #6866ef);
  box-shadow: 0 0 15px rgba(18, 16, 85, 0.4);
}

.card-enterprise-border {
  border: 2px solid transparent;
  background-origin: border-box;
  background-clip: padding-box, border-box;
  background-image: 
    linear-gradient(to bottom, hsl(var(--card)), hsl(var(--card))), 
    linear-gradient(45deg, #1e1b4b, #121055);
  box-shadow: 0 0 15px rgba(30, 27, 75, 0.4);
}

/* Dark mode adjustments for card borders */
.dark .card-lite-border {
  box-shadow: 0 0 12px rgba(56, 180, 139, 0.25);
}
.dark .card-pro-border {
  box-shadow: 0 0 12px rgba(104, 102, 239, 0.25);
}
.dark .card-pro-plus-border {
  box-shadow: 0 0 12px rgba(182, 109, 208, 0.25);
}
.dark .card-team-border {
  box-shadow: 0 0 12px rgba(18, 16, 85, 0.25);
}
.dark .card-enterprise-border {
  box-shadow: 0 0 12px rgba(30, 27, 75, 0.25);
}

@keyframes gradientAnimation {
  0% { background-position: 0% 50%; }
  50% { background-position: 100% 50%; }
  100% { background-position: 0% 50%; }
}
`;

// Define types for subscription plans
interface SubscriptionPlan {
  id: string;
  name: string;
  description: string;
  price_monthly_usd: number;
  price_yearly_usd: number;
  trial_days: number;
  max_flows: number;
  monthly_quota_credits: number;
  max_flow_runs_per_day: number;
  max_concurrent_flows: number;
  max_kb_storage_mb: number;
  max_kbs_per_user: number;
  max_kb_entries_per_kb: number;
  max_tokens_per_kb_entry: number;
  max_kb_queries_per_day: number;
  allows_overage: boolean;
  allows_rollover: boolean;
  overage_price_per_credit: number;
  features: Record<string, boolean>;
  allowed_models: Record<string, boolean>;
  allowed_premium_tools: Record<string, boolean>;
  is_active: boolean;
  stripe_product_id: string | null;
  stripe_default_price_id: string | null;
  created_at?: string;
  default_overage_limit_usd?: number;
}

export default function CheckoutPage(): JSX.Element {
  const [isYearly, setIsYearly] = useState<boolean>(false);
  const [isLoading, setIsLoading] = useState<Record<string, boolean>>({});
  const [subscriptionPlans, setSubscriptionPlans] = useState<SubscriptionPlan[]>([]);
  const [isLoadingPlans, setIsLoadingPlans] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showPlanChangeModal, setShowPlanChangeModal] = useState(false);
  const [selectedPlanId, setSelectedPlanId] = useState<string | null>(null);
  const [currentPlanName, setCurrentPlanName] = useState<string>("");
  const [currentPlanId, setCurrentPlanId] = useState<string | null>(null);
  
  // State for horizontal scroll
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const [canScrollLeft, setCanScrollLeft] = useState(false);
  const [canScrollRight, setCanScrollRight] = useState(false);
  
  const navigate = useCustomNavigate();
  const setErrorData = useAlertStore((state) => state.setErrorData);
  const cookies = new Cookies();
  const setHasChosenPlan = useAuthStore((state) => state.setHasChosenPlan);
  const { mutate: confirmPlan, isPending: isConfirmingPlan } = useConfirmPlanSelection();

  // Check authentication before proceeding
  useEffect(() => {
    const checkAuth = async () => {
      try {
        const token = cookies.get(LANGFLOW_ACCESS_TOKEN);
        if (!token) {
          navigate("/login?redirect=/billing/plans");
          return;
        }
        
        // Get current subscription plan from localStorage
        const currentSubPlanId = localStorage.getItem('current_subscription_plan_id');
        if (currentSubPlanId) {
          setCurrentPlanId(currentSubPlanId);
        }
      } catch (error) {
        navigate("/login?redirect=/billing/plans");
      }
    };
    
    checkAuth();
  }, [navigate]);

  // Fetch subscription plans from the backend
  useEffect(() => {
    const fetchSubscriptionPlans = async () => {
      try {
        setIsLoadingPlans(true);
        // Use the api client from the project
        const response = await api.get('/api/v1/billing/subscription-plans');
        
        // Filter out inactive plans if needed (assuming the backend already filters, but just in case)
        const activePlans = response.data.filter((plan: SubscriptionPlan) => plan.is_active);
        setSubscriptionPlans(activePlans);
        setError(null);
      } catch (error) {
        console.error('Error fetching subscription plans:', error);
        setError('Failed to load subscription plans. Please try again later.');
        setErrorData({
          title: 'Error Loading Plans',
          list: ['Failed to load subscription plans. Please try again later.'],
        });
      } finally {
        setIsLoadingPlans(false);
      }
    };

    fetchSubscriptionPlans();
  }, [setErrorData]);

  // Check scroll button visibility
  const checkScrollButtons = useCallback(() => {
    const container = scrollContainerRef.current;
    if (container) {
      const { scrollLeft, scrollWidth, clientWidth } = container;
      setCanScrollLeft(scrollLeft > 0);
      // Add a small tolerance (e.g., 1px) for floating point inaccuracies
      setCanScrollRight(scrollLeft < scrollWidth - clientWidth - 1);
    } else {
      setCanScrollLeft(false);
      setCanScrollRight(false);
    }
  }, []);

  // Effect to check scroll buttons on mount and resize
  useEffect(() => {
    checkScrollButtons();
    window.addEventListener('resize', checkScrollButtons);
    return () => window.removeEventListener('resize', checkScrollButtons);
  }, [subscriptionPlans, checkScrollButtons]);
  
  // Effect to check scroll buttons when plans load
  useEffect(() => {
    if (!isLoadingPlans) {
      // Timeout to allow layout to settle
      const timer = setTimeout(checkScrollButtons, 100); 
      return () => clearTimeout(timer);
    }
  }, [isLoadingPlans, checkScrollButtons]);

  // Function to handle horizontal scroll
  const handleScroll = (direction: 'left' | 'right') => {
    const container = scrollContainerRef.current;
    if (container) {
      const scrollAmount = container.clientWidth * 0.8; // Scroll by 80% of visible width
      container.scrollBy({
        left: direction === 'left' ? -scrollAmount : scrollAmount,
        behavior: 'smooth',
      });
      // Re-check buttons after scroll animation might start
      // Use a timeout because scroll event might not fire immediately
      setTimeout(checkScrollButtons, 300); 
    }
  };

  // Function to create a Stripe checkout session
  const handleCreateCheckoutSession = async (planId: string) => {
    try {
      setIsLoading(prev => ({ ...prev, [planId]: true }));
      
      // Save selected plan ID to localStorage for the success page to use
      localStorage.setItem('selected_plan_id', planId);
      
      // Get the current URL to build success and cancel URLs
      const baseUrl = window.location.origin;
      const successUrl = `${baseUrl}/billing/success`;
      const cancelUrl = `${baseUrl}/billing/cancel`;
      
      // For existing subscribers, check if they're trying to change plans
      const currentPlan = subscriptionPlans.find(plan => 
        plan.id === localStorage.getItem('current_subscription_plan_id')
      );
      
      // If they already have a subscription and are trying to change plans
      if (currentPlan && currentPlan.id !== planId) {
        // Determine if the user is downgrading
        const currentPlanIndex = subscriptionPlans.findIndex(plan => plan.id === currentPlan.id);
        const targetPlanIndex = subscriptionPlans.findIndex(plan => plan.id === planId);
        
        const isDowngrade = currentPlanIndex > targetPlanIndex;
        
        // Only show confirmation for downgrades
        if (isDowngrade) {
          setSelectedPlanId(planId);
          setCurrentPlanName(currentPlan.name);
          setShowPlanChangeModal(true);
          return;
        }
        
        // For upgrades, proceed directly
        const changePlanUrl = `/api/v1/stripe/create-checkout-session?plan_id=${planId}&success_url=${encodeURIComponent(successUrl)}&cancel_url=${encodeURIComponent(cancelUrl)}&change_plan=true`;
        
        const response = await api.post(changePlanUrl);
        window.location.href = response.data.checkout_url;
        return;
      }
      
      // Normal flow for new subscriptions
      const response = await api.post(
        `/api/v1/stripe/create-checkout-session?plan_id=${planId}&success_url=${encodeURIComponent(successUrl)}&cancel_url=${encodeURIComponent(cancelUrl)}`
      );
      
      // Redirect to Stripe Checkout
      window.location.href = response.data.checkout_url;
      
    } catch (error: any) {
      console.error('Error creating checkout session:', error);
      let errorMessage = 'Failed to create checkout session';
      
      if (error?.response) {
        if (error.response.status === 403) {
          errorMessage = 'You need to be authenticated to subscribe to a plan. Please log in.';
          navigate('/login?redirect=/billing/plans');
        } else if (error.response.status === 500 && error.response.data?.detail?.includes('Failed to create Stripe customer')) {
          errorMessage = 'Unable to create your customer profile. Please ensure your account information is complete and try again.';
          
          // Offer to redirect to profile settings
          if (window.confirm('Your profile information may be incomplete. Would you like to update your profile settings?')) {
            navigate('/settings/profile');
            return;
          }
        } else {
          errorMessage = error.response.data.detail || errorMessage;
        }
      } else if (error instanceof Error) {
        errorMessage = error.message;
      }
      
      setErrorData({
        title: 'Checkout Error',
        list: [errorMessage],
      });
    } finally {
      setIsLoading(prev => ({ ...prev, [planId]: false }));
    }
  };

  // Function to continue with plan change after confirmation
  const handleConfirmPlanChange = () => {
    if (!selectedPlanId) return;
    
    const baseUrl = window.location.origin;
    const successUrl = `${baseUrl}/billing/success`;
    const cancelUrl = `${baseUrl}/billing/cancel`;
    
    // Add a parameter to indicate this is a plan change (backend can handle accordingly)
    const changePlanUrl = `/api/v1/stripe/create-checkout-session?plan_id=${selectedPlanId}&success_url=${encodeURIComponent(successUrl)}&cancel_url=${encodeURIComponent(cancelUrl)}&change_plan=true`;
    
    api.post(changePlanUrl)
      .then(response => {
        window.location.href = response.data.checkout_url;
      })
      .catch(changeError => {
        // If we get a currency conflict error
        if (changeError?.response?.data?.detail?.includes('combine currencies')) {
          const planChangeMessage = 
            "Cannot change subscription due to currency differences. " +
            "Please contact support to help you change your subscription plan.";
            
          setErrorData({
            title: 'Currency Conflict',
            list: [planChangeMessage],
          });
        } else {
          // For other errors, continue with normal error handling
          throw changeError;
        }
      })
      .finally(() => {
        if (selectedPlanId) {
          setIsLoading(prev => ({ ...prev, [selectedPlanId]: false }));
        }
      });
  };

  // Get formatted price based on billing period
  const getFormattedPrice = (plan: SubscriptionPlan) => {
    const price = isYearly ? plan.price_yearly_usd : plan.price_monthly_usd;
    
    if (price === 0) return "$0";
    
    const monthlyPrice = isYearly 
      ? (plan.price_yearly_usd / 12).toFixed(2)
      : plan.price_monthly_usd.toFixed(2);
      
    return isYearly 
      ? `$${monthlyPrice}/mo ($${plan.price_yearly_usd.toFixed(2)}/year)`
      : `$${monthlyPrice}/mo`;
  };

  // Format features for display
  const formatFeatureName = (feature: string): string => {
    return feature
      .split('_')
      .map(word => word.charAt(0).toUpperCase() + word.slice(1))
      .join(' ');
  };

  // Helper function to get styling based on plan name
  const getPlanStyling = (planName: string) => {
    const baseCard = "bg-card rounded-lg h-full flex flex-col"; // Inner card needs bg and rounding
    const baseText = "text-card-foreground";
    const baseCheck = "text-primary";
    const basePrice = "text-primary";

    switch (planName) {
      case "Free":
        return {
          cardClass: "bg-card border border-border rounded-lg shadow-md h-full flex flex-col", // Standard border
          textClass: baseText,
          priceClass: basePrice,
          checkClass: baseCheck,
          buttonVariant: "outline" as const,
          buttonClass: "", 
          isPopular: false,
        };
      case "Lite":
        return {
          cardClass: `${baseCard} card-lite-border`,
          textClass: baseText,
          priceClass: basePrice,
          checkClass: baseCheck,
          buttonVariant: "default" as const,
          buttonClass: "",
          isPopular: false,
        };
      case "Pro":
        return {
          cardClass: `${baseCard} card-pro-border`,
          textClass: baseText,
          priceClass: basePrice,
          checkClass: baseCheck,
          buttonVariant: "default" as const,
          buttonClass: "bg-primary hover:bg-primary/90",
          isPopular: true, // Flag to mark as popular
        };
      case "Pro Plus":
        return {
          cardClass: `${baseCard} card-pro-plus-border`,
          textClass: baseText,
          priceClass: basePrice,
          checkClass: baseCheck,
          buttonVariant: "default" as const,
          buttonClass: "",
          isPopular: false,
        };
      case "Team":
        return {
          cardClass: `${baseCard} card-team-border`,
          textClass: baseText,
          priceClass: basePrice,
          checkClass: baseCheck,
          buttonVariant: "default" as const,
          buttonClass: "",
          isPopular: false,
          isBestForSMBs: true, // Flag to mark as best for SMBs
        };
      case "Enterprise":
        return {
          cardClass: `${baseCard} card-enterprise-border`,
          textClass: baseText,
          priceClass: basePrice,
          checkClass: baseCheck,
          buttonVariant: "outline" as const, // Keep outline for contact
          buttonClass: "", 
          isPopular: false,
        };
      default:
        return { // Fallback to default styling
          cardClass: "bg-card border rounded-lg h-full flex flex-col",
          textClass: baseText,
          priceClass: basePrice,
          checkClass: baseCheck,
          buttonVariant: "default" as const,
          buttonClass: "",
          isPopular: false,
        };
    }
  };

  // Function to handle plan change confirmation and cancellation
  const handlePlanChangeModal = {
    confirm: (_, data) => {
      setSelectedPlanId(data);
      handleConfirmPlanChange();
      setShowPlanChangeModal(false);
    },
    cancel: () => {
      if (selectedPlanId) {
        setIsLoading(prev => ({ ...prev, [selectedPlanId]: false }));
      }
      setSelectedPlanId(null);
      setShowPlanChangeModal(false);
    },
    close: () => {
      if (selectedPlanId) {
        setIsLoading(prev => ({ ...prev, [selectedPlanId]: false }));
      }
      setSelectedPlanId(null);
      setShowPlanChangeModal(false);
    }
  };

  // Function to handle choosing the Free plan
  const handleChooseFreePlan = () => {
    confirmPlan(undefined, {
      onSuccess: () => {
        setHasChosenPlan(true);
        navigate("/home");
      },
      onError: (error) => {
        console.error("Error confirming free plan selection:", error);
        setErrorData({
          title: "Error Saving Choice",
          list: ["Could not confirm your selection. Please try again."],
        });
      },
    });
  };

  // Loading state
  if (isLoadingPlans) {
    return (
      <div className="flex h-screen w-full items-center justify-center bg-muted">
        <div className="flex flex-col items-center gap-4">
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
          <p>Loading subscription plans...</p>
        </div>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className="flex h-screen w-full items-center justify-center bg-muted">
        <div className="flex flex-col items-center gap-4 text-center max-w-md px-4">
          <div className="text-destructive text-lg font-semibold">Unable to load subscription plans</div>
          <p>{error}</p>
          <Button 
            onClick={() => window.location.reload()}
            className="mt-4"
          >
            Try Again
          </Button>
        </div>
      </div>
    );
  }

  return (
    <Form.Root className="w-full h-screen flex flex-col">
      {/* Add the style tag with our animation CSS */}
      <style dangerouslySetInnerHTML={{ __html: animatedGradientBadgeStyle }} />
      <div className="flex flex-1 w-full flex-col items-center bg-muted pb-12 overflow-y-auto">
        {/* Header */}
        <div className="flex w-full items-center justify-center border-b bg-background py-4 shadow-sm sticky top-0 z-10 bg-opacity-95 backdrop-blur-sm">
          <div className="flex items-center gap-2">
            
            <div className="flex flex-col items-center gap-3">
              <span className="text-3xl font-semibold text-primary">
                Plans and Pricing
              </span>
              <span className="text-sm text-muted-foreground">
                Build and deploy powerful AI agents—no code, no limits.
              </span>
            </div>

          </div>
        </div>

        {/* Billing Toggle */}
        {/* <div className="my-8 flex items-center gap-4">
          <span className={cn("text-sm", !isYearly && "font-medium")}>Monthly</span>
          <Switch
            checked={isYearly}
            onCheckedChange={setIsYearly}
            className="data-[state=checked]:bg-primary"
          />
          <div className="flex items-center gap-2">
            <span className={cn("text-sm", isYearly && "font-medium")}>Yearly</span>
            <Badge variant="outline" className="bg-primary/10 text-primary">
              Save up to 20%
            </Badge>
          </div>
        </div> */}

        {/* Plans Section */}
        <div className="w-full max-w-[100%] px-4 relative pt-8 mb-12 border-b">
          {subscriptionPlans.length === 0 && !isLoadingPlans ? (
          <div className="flex h-64 w-full items-center justify-center">
            <p className="text-muted-foreground">No subscription plans available at the moment.</p>
          </div>
          ) : !isLoadingPlans && (
            <div className="relative">
              {/* Scroll Left Button */}
              <Button
                variant="outline"
                size="default"
                className={cn(
                  "absolute left-0 top-1/2 z-10 -translate-y-1/2 transform rounded-full shadow-md transition-opacity",
                  !canScrollLeft && "opacity-0 pointer-events-none"
                )}
                onClick={() => handleScroll('left')}
                aria-label="Scroll left"
              >
                <ForwardedIconComponent name="ChevronLeft" className="h-36 w-36" />
              </Button>
              
              {/* Left Fade Effect */}
              {canScrollLeft && (
                <div className="absolute inset-y-0 left-0 w-64 bg-gradient-to-r from-muted/80 to-transparent backdrop-filter backdrop-blur-[1px] pointer-events-none z-5" />
              )}

              {/* Scrollable Container */}
              <div 
                ref={scrollContainerRef}
                className="flex space-x-6 overflow-x-auto scroll-smooth scrollbar-hide py-4 px-2 pt-12 overflow-visible"
                onScroll={checkScrollButtons}
              >
                {subscriptionPlans.map((plan, index) => {
                  // Get dynamic styling based on plan name
                  const styling = getPlanStyling(plan.name);
                  
                  // Base container div styles
                  const containerBase = "flex w-[320px] shrink-0 flex-col overflow-hidden transition-all duration-200";

                  // Conditionally render wrapper for non-Free plans
                  if (plan.name !== "Free") {
                    return (
                      <div key={plan.id} className={cn(containerBase, "overflow-visible")}>
                        <Card className={cn(styling.cardClass)}> 
                          {/* Card Header */}                          
                          <CardHeader className={cn("pb-2", styling.textClass)}>
                            {/* {plan.trial_days > 0 && (
                              <Badge variant="secondary" className="mb-2 w-fit bg-secondary/80">
                      {plan.trial_days} day trial
                    </Badge>
                            )} */}
                            <div className="flex items-center gap-2">
                              <CardTitle className="text-xl">{plan.name === "Pro Plus" ? "Pro+" : plan.name}</CardTitle>
                              {styling.isPopular && (
                                <Badge variant="default" className="px-2 py-0.5 text-xs animated-gradient-badge text-white">
                                  Most Popular
                                </Badge>
                              )}
                              {styling.isBestForSMBs && (
                                <Badge variant="default" className="px-2 py-0.5 text-xs smb-animated-gradient-badge text-white">
                                  Best for SMBs
                                </Badge>
                              )}
                            </div>
                            <CardDescription className="min-h-[50px] flex items-center">{plan.description}</CardDescription>
                            <div className="mt-4 min-h-[70px] flex flex-col justify-end">
                              <div className={cn("text-3xl font-bold", styling.priceClass)}>
                                {(plan.name as string) === "Enterprise" ? "Let's talk" : getFormattedPrice(plan)}
                              </div>
                              <div className="mt-1 text-xs text-muted-foreground">
                                {(plan.name as string) === "Enterprise" ? 
                                  "\u00A0" /* Non-breaking space to maintain height */
                                  : plan.price_monthly_usd > 0 
                                    ? (isYearly ? "Billed annually" : "Billed monthly") 
                                    : "per month / forever free"}
                              </div>
                              <div className="mt-4">
                                {plan.id === currentPlanId ? (
                                  <div className="w-full flex items-center justify-center gap-2 py-2 rounded-md bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-400 text-sm font-medium border border-green-200 dark:border-green-800">
                                    <Check className="h-4 w-4" />
                                    <span className="text-s">Your Current Plan</span>
                                  </div>
                                ) : (
                                  <Button 
                                    variant={styling.buttonVariant}
                                    className={cn("w-full", styling.buttonClass, "flex items-center justify-center")}
                                    onClick={() => {
                                      if (plan.name === "Enterprise") {
                                        window.location.href = "mailto:contact@langflow.ai?subject=Enterprise Plan Inquiry";
                                      } else {
                                        handleCreateCheckoutSession(plan.id);
                                      }
                                    }}
                                    disabled={isLoading[plan.id]}
                                  >
                                    {isLoading[plan.id] ? (
                                      <>
                                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                        Processing...
                                      </>
                                    ) : plan.name === "Enterprise" ? (
                                      "Contact sales"
                                    ) : (
                                      "Get  " + (plan.name as string === "Pro Plus" ? "Pro+" : plan.name)
                                    )}
                                  </Button>
                                )}
                              </div>
                            </div>
                          </CardHeader>
                          
                          {/* Card Content */}                          
                          <CardContent className={cn("flex-1 pt-4", styling.textClass)}>
                            <div className="space-y-4">
                              {/* Plan Limits & Features */}
                              <div className="space-y-2">
                                <h4 className="font-medium">Limits & Quotas</h4>
                                <ul className="space-y-2 text-sm">
                                  <li className="flex items-start gap-2">
                                    <Check className={cn("h-4 w-4 mt-0.5 shrink-0", styling.checkClass)} />
                                    <span>{plan.monthly_quota_credits.toLocaleString()} credits per month</span>
                                  </li>
                                  <li className="flex items-start gap-2">
                                    <Check className={cn("h-4 w-4 mt-0.5 shrink-0", styling.checkClass)} />
                                    <span>{plan.max_flows === 0 ? "Unlimited" : plan.max_flows} flows</span>
                                  </li>
                                  <li className="flex items-start gap-2">
                                    <Check className={cn("h-4 w-4 mt-0.5 shrink-0", styling.checkClass)} />
                                    <span>{plan.max_concurrent_flows} concurrent {plan.max_concurrent_flows === 1 ? "flow" : "flows"}</span>
                                  </li>
                                  <li className="flex items-start gap-2">
                                    <Check className={cn("h-4 w-4 mt-0.5 shrink-0", styling.checkClass)} />
                                    <span>{plan.max_flow_runs_per_day === 0 ? "Unlimited" : plan.max_flow_runs_per_day} runs per day</span>
                                  </li>
                                  <li className="flex items-start gap-2">
                                    <Check className={cn("h-4 w-4 mt-0.5 shrink-0", styling.checkClass)} />
                                    <span>{plan.max_kb_storage_mb} MB KB storage</span>
                                  </li>
                                </ul>
                              </div>
                              
                              {/* Models */}
                              <div className="space-y-2">
                                <h4 className="font-medium">Models</h4>
                                <div className="flex flex-wrap gap-1">
                                  {Object.keys(plan.allowed_models).length === 0 ? (
                                    <span className="text-sm">Custom models available</span>
                                  ) : (
                                    Object.keys(plan.allowed_models).map((model) => (
                                      <Badge key={model} variant="successStatic" size="sm">
                                        {model}
                                      </Badge>
                                    ))
                                  )}
                                </div>
                              </div>
                              
                              {/* Features */}
                              <div className="space-y-2">
                                <h4 className="font-medium">{plan.name} Features</h4>
                                <ul className="space-y-2 text-sm">
                                  {/* Add "Everything in..." feature */}
                                  {index > 0 && subscriptionPlans[index - 1] && (
                                    <span className="font-bold">Everything in {subscriptionPlans[index - 1].name} and:</span>
                                  )}
                                  {Object.entries(plan.features).map(([feature, enabled]) => (
                                    enabled && (
                                      <li key={feature} className="flex items-start gap-2">
                                        <Check className={cn("h-4 w-4 mt-0.5 shrink-0", styling.checkClass)} />
                                        <span>{formatFeatureName(feature)}</span>
                                      </li>
                                    )
                                  ))}
                                  {plan.allows_overage && (
                                    <li className="flex items-start gap-2">
                                      <Check className={cn("h-4 w-4 mt-0.5 shrink-0", styling.checkClass)} />
                                      <span>Overage available (${plan.overage_price_per_credit}/credit)</span>
                                    </li>
                                  )}
                                  {plan.allows_rollover && (
                                    <li className="flex items-start gap-2">
                                      <Check className={cn("h-4 w-4 mt-0.5 shrink-0", styling.checkClass)} />
                                      <span>Unused credits roll over</span>
                                    </li>
                                  )}
                                  {Object.keys(plan.allowed_premium_tools).length > 0 && (
                                    <li className="flex items-start gap-2">
                                      <Check className={cn("h-4 w-4 mt-0.5 shrink-0", styling.checkClass)} />
                                      <span>Premium tools: {Object.keys(plan.allowed_premium_tools).map(formatFeatureName).join(", ")}</span>
                                    </li>
                                  )}
                                </ul>
                              </div>
                            </div>
                          </CardContent>
                          
                          {/* Card Footer */}                          
                          {/* <CardFooter className={cn("pt-4 mt-auto", styling.textClass)}>
                            {plan.id === currentPlanId ? (
                              <div className="w-full flex items-center justify-center gap-2 py-2 rounded-md bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-400 text-sm font-medium border border-green-200 dark:border-green-800">
                                <Check className="h-4 w-4" />
                                <span className="text-s">Your Current Plan</span>
                              </div>
                            ) : (
                              <Button 
                                variant={styling.buttonVariant}
                                className={cn("w-full", styling.buttonClass, "flex items-center justify-center")}
                                onClick={() => {
                                  if (plan.name === "Enterprise") {
                                    window.location.href = "mailto:contact@langflow.ai?subject=Enterprise Plan Inquiry";
                                  } else {
                                    handleCreateCheckoutSession(plan.id);
                                  }
                                }}
                                disabled={isLoading[plan.id]}
                              >
                                {isLoading[plan.id] ? (
                                  <>
                                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                    Processing...
                                  </>
                                ) : plan.name === "Enterprise" ? (
                                  "Contact sales"
                                ) : (
                                  "Get  " + (plan.name as string === "Pro Plus" ? "Pro+" : plan.name)
                                )}
                              </Button>
                            )}
                          </CardFooter> */}
                        </Card>
                      </div>
                    );
                  } else {
                    // Render Free plan without the gradient wrapper
                    return (
                      <Card 
                        key={plan.id} 
                        className={cn(containerBase, styling.cardClass)}
                      >
                        <CardHeader className={cn("pb-2", styling.textClass)}>
                          {plan.trial_days > 0 && (
                            <Badge variant="secondary" className="mb-2 w-fit bg-secondary/80">
                              {plan.trial_days} day trial
                            </Badge>
                          )}
                          <div className="flex items-center gap-2">
                            <CardTitle className="text-xl">{plan.name as string === "Pro Plus" ? "Pro+" : plan.name}</CardTitle>
                            {styling.isPopular && (
                              <Badge variant="default" className="px-2 py-0.5 text-xs animated-gradient-badge text-white">
                                Most Popular
                              </Badge>
                            )}
                            {styling.isBestForSMBs && (
                              <Badge variant="default" className="px-2 py-0.5 text-xs smb-animated-gradient-badge text-white">
                                Best for SMBs
                              </Badge>
                            )}
                          </div>
                          <CardDescription className="min-h-[50px] flex items-center">{plan.description}</CardDescription>
                          <div className="mt-4 min-h-[70px] flex flex-col justify-end">
                            <div className={cn("text-3xl font-bold", styling.priceClass)}>
                              {(plan.name as string) === "Enterprise" ? "Let's Talk" : getFormattedPrice(plan)}
                            </div>
                            <div className="mt-1 text-xs text-muted-foreground">
                              {(plan.name as string) === "Enterprise" ? 
                                "\u00A0" /* Non-breaking space to maintain height */
                                : plan.price_monthly_usd > 0 
                                  ? (isYearly ? "Billed annually" : "Billed monthly") 
                                  : "per month / forever free"}
                            </div>
                            <div className="mt-4">
                              <Button 
                                variant={styling.buttonVariant}
                                className={cn("w-full", styling.buttonClass, "flex items-center justify-center")}
                                onClick={handleChooseFreePlan}
                                disabled={isConfirmingPlan}
                              >
                                {isConfirmingPlan ? (
                                  <>
                                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                    Confirming...
                                  </>
                                ) : (
                                  "Choose Later"
                                )}
                              </Button>
                            </div>
                          </div>
                        </CardHeader>
                        
                        {/* Card Content */}                        
                        <CardContent className={cn("flex-1 pt-4", styling.textClass)}>
                          <div className="space-y-4">
                            {/* Plan Limits & Features */}
                            <div className="space-y-2">
                              <h4 className="font-medium">Limits & Quotas</h4>
                              <ul className="space-y-2 text-sm">
                                <li className="flex items-start gap-2">
                                  <Check className={cn("h-4 w-4 mt-0.5 shrink-0", styling.checkClass)} />
                                  <span>{plan.monthly_quota_credits.toLocaleString()} credits per month</span>
                                </li>
                                <li className="flex items-start gap-2">
                                  <Check className={cn("h-4 w-4 mt-0.5 shrink-0", styling.checkClass)} />
                                  <span>{plan.max_flows === 0 ? "Unlimited" : plan.max_flows} flows</span>
                                </li>
                                <li className="flex items-start gap-2">
                                  <Check className={cn("h-4 w-4 mt-0.5 shrink-0", styling.checkClass)} />
                                  <span>{plan.max_concurrent_flows} concurrent {plan.max_concurrent_flows === 1 ? "flow" : "flows"}</span>
                                </li>
                                <li className="flex items-start gap-2">
                                  <Check className={cn("h-4 w-4 mt-0.5 shrink-0", styling.checkClass)} />
                                  <span>{plan.max_flow_runs_per_day === 0 ? "Unlimited" : plan.max_flow_runs_per_day} runs per day</span>
                                </li>
                                <li className="flex items-start gap-2">
                                  <Check className={cn("h-4 w-4 mt-0.5 shrink-0", styling.checkClass)} />
                                  <span>{plan.max_kb_storage_mb} MB KB storage</span>
                                </li>                                  
                              </ul>
                            </div>
                            
                            {/* Models */}
                            <div className="space-y-2">
                              <h4 className="font-medium">Models</h4>
                              <div className="flex flex-wrap gap-1">
                                {Object.keys(plan.allowed_models).length === 0 ? (
                                  <span className="text-sm">Custom models available</span>
                                ) : (
                                  Object.keys(plan.allowed_models).map((model) => (
                                    <Badge key={model} variant="secondary" size="sm">
                                      {model}
                                    </Badge>
                                  ))
                                )}
                              </div>
                            </div>
                            
                            {/* Features */}
                            <div className="space-y-2">
                              <h4 className="font-medium">Features</h4>
                              <ul className="space-y-2 text-sm">
                                {/* NOTE: No "Everything in..." for the Free plan */}
                                {Object.entries(plan.features).map(([feature, enabled]) => (
                                  enabled && (
                                    <li key={feature} className="flex items-start gap-2">
                                      <Check className={cn("h-4 w-4 mt-0.5 shrink-0", styling.checkClass)} />
                                      <span>{formatFeatureName(feature)}</span>
                                    </li>
                                  )
                                ))}
                                {plan.allows_overage && (
                                  <li className="flex items-start gap-2">
                                    <Check className={cn("h-4 w-4 mt-0.5 shrink-0", styling.checkClass)} />
                                    <span>Overage available (${plan.overage_price_per_credit}/credit)</span>
                                  </li>
                                )}
                                {plan.allows_rollover && (
                                  <li className="flex items-start gap-2">
                                    <Check className={cn("h-4 w-4 mt-0.5 shrink-0", styling.checkClass)} />
                                    <span>Unused credits roll over</span>
                                  </li>
                                )}
                                {Object.keys(plan.allowed_premium_tools).length > 0 && (
                                  <li className="flex items-start gap-2">
                                    <Check className={cn("h-4 w-4 mt-0.5 shrink-0", styling.checkClass)} />
                                    <span>Premium tools: {Object.keys(plan.allowed_premium_tools).map(formatFeatureName).join(", ")}</span>
                                  </li>
                                )}
                              </ul>
                            </div>
                          </div>
                        </CardContent>

                        {/* Card Footer */}                          
                        <CardFooter className={cn("pt-4 mt-auto", styling.textClass)}> 
                          {/* Button moved to appear under the price */}
                        </CardFooter>
                      </Card>
                    );
                  }
                 })}
               </div>

              {/* Scroll Right Button */}
              <Button
                variant="outline"
                size="default"
                className={cn(
                  "absolute right-0 top-1/2 z-10 -translate-y-1/2 transform rounded-full shadow-md transition-opacity",
                  !canScrollRight && "opacity-0 pointer-events-none"
                )}
                onClick={() => handleScroll('right')}
                aria-label="Scroll right"
              >
                <ForwardedIconComponent name="ChevronRight" className="h-36 w-36" />
              </Button>

              {/* Right Fade Effect */}
              {canScrollRight && (
                <div className="absolute inset-y-0 right-0 w-64 bg-gradient-to-l from-muted/80 to-transparent backdrop-filter backdrop-blur-[1px] pointer-events-none z-5" />
              )}
          </div>
        )}
        </div>

        {/* Plan Change Confirmation Modal */}
        <ConfirmationModal
          open={showPlanChangeModal}
          onClose={handlePlanChangeModal.close}
          title="Downgrade Confirmation"
          confirmationText="Continue with Downgrade"
          cancelText="Cancel"
          size="x-small"
          data={selectedPlanId}
          index={0}
          onConfirm={handlePlanChangeModal.confirm}
          onCancel={handlePlanChangeModal.cancel}
        >
          <ConfirmationModal.Content>
            <div className="py-2">
              <p className="mb-2">You are about to downgrade from <strong>{currentPlanName}</strong> to a lower tier plan.</p>
              <p>This may affect your available features and limits. Downgrading may result in the immediate loss of access to premium features and any data exceeding the new plan's limits could be at risk.</p>
              <p className="mt-2 text-sm text-amber-600 dark:text-amber-400">Note: Downgrading plans may require canceling your current subscription first.</p>
            </div>
          </ConfirmationModal.Content>
        </ConfirmationModal>
      </div>
    </Form.Root>
  );
} 