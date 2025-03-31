import IconComponent from "@/components/common/genericIconComponent";
import ShadTooltip from "@/components/common/shadTooltipComponent";
import { Button } from "@/components/ui/button";
import { useUtilityStore } from "@/stores/utilityStore";
import { cn } from "@/utils/utils";
import { ButtonHTMLAttributes, useState, useEffect, useRef } from "react";

export function EditMessageButton({
  onEdit,
  onCopy,
  onEvaluate,
  isBotMessage,
  evaluation,
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  onEdit: () => void;
  onCopy: () => void;
  onDelete: () => void;
  onEvaluate?: (value: boolean | null) => void;
  isBotMessage?: boolean;
  evaluation?: boolean | null;
}) {
  const [isCopied, setIsCopied] = useState(false);
  const [localEvaluation, setLocalEvaluation] = useState<boolean | null>(evaluation || null);
  // Get the utility store functions for auto-scroll control
  const setDisableAutoScroll = useUtilityStore((state) => state.setDisableAutoScroll);
  // Save scroll position when evaluating
  const scrollPositionRef = useRef<number | null>(null);

  useEffect(() => {
    if (evaluation !== undefined) {
      setLocalEvaluation(evaluation);
    }
  }, [evaluation]);

  const handleCopy = () => {
    onCopy();
    setIsCopied(true);
    setTimeout(() => setIsCopied(false), 2000);
  };

  const handleEvaluate = (value: boolean) => {
    // Store the current scroll position
    scrollPositionRef.current = document.documentElement.scrollTop || document.body.scrollTop;
    
    // Disable auto-scrolling before updating the evaluation
    setDisableAutoScroll(true);
    
    // Update the evaluation state
    const newValue = localEvaluation === value ? null : value;
    setLocalEvaluation(newValue);
    
    // Call the evaluation callback which will update the message
    onEvaluate?.(newValue);
    
    // After a short delay, restore the scroll position and re-enable auto-scrolling
    setTimeout(() => {
      if (scrollPositionRef.current !== null) {
        // Restore the scroll position
        window.scrollTo({
          top: scrollPositionRef.current,
          behavior: 'auto'
        });
        
        // Clear the stored position
        scrollPositionRef.current = null;
        
        // Re-enable auto-scrolling after the scroll position is restored
        setTimeout(() => {
          setDisableAutoScroll(false);
        }, 100);
      }
    }, 10);
  };

  return (
    <div className="flex items-center rounded-md bg-background/95 scale-90">
      {!isBotMessage && (
        <ShadTooltip styleClasses="z-50" content="Edit message" side="bottom">
          <div className="p-0.5">
            <Button
              variant="ghost"
              size="iconSm"
              onClick={onEdit}
              className="h-6 w-6"
            >
              <IconComponent name="Pen" className="h-3 w-3" />
            </Button>
          </div>
        </ShadTooltip>
      )}

      <ShadTooltip
        styleClasses="z-50"
        content={isCopied ? "Copied!" : "Copy message"}
        side="bottom"
      >
        <div className="p-0.5">
          <Button
            variant="ghost"
            size="iconSm"
            onClick={handleCopy}
            className="h-6 w-6"
          >
            <IconComponent
              name={isCopied ? "Check" : "Copy"}
              className="h-3 w-3"
            />
          </Button>
        </div>
      </ShadTooltip>

      {isBotMessage && (
        <div className="flex">
          <ShadTooltip styleClasses="z-50" content="Helpful" side="bottom">
            <div className="p-0.5">
              <Button
                variant="ghost"
                size="iconSm"
                onClick={(e) => {
                  // Prevent default browser behavior
                  e.preventDefault();
                  e.stopPropagation();
                  handleEvaluate(true);
                }}
                className="h-6 w-6"
                data-testid="helpful-button"
              >
                <IconComponent
                  name={localEvaluation === true ? "ThumbUpIconCustom" : "ThumbsUp"}
                  className={cn("h-3 w-3")}
                />
              </Button>
            </div>
          </ShadTooltip>

          <ShadTooltip styleClasses="z-50" content="Not helpful" side="bottom">
            <div className="p-0.5">
              <Button
                variant="ghost"
                size="iconSm"
                onClick={(e) => {
                  // Prevent default browser behavior
                  e.preventDefault();
                  e.stopPropagation();
                  handleEvaluate(false);
                }}
                className="h-6 w-6"
                data-testid="not-helpful-button"
              >
                <IconComponent
                  name={
                    localEvaluation === false ? "ThumbDownIconCustom" : "ThumbsDown"
                  }
                  className={cn("h-3 w-3")}
                />
              </Button>
            </div>
          </ShadTooltip>
        </div>
      )}
    </div>
  );
}
