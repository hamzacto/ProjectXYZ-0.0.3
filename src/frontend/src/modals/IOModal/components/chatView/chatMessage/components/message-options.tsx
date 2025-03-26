import IconComponent from "@/components/common/genericIconComponent";
import ShadTooltip from "@/components/common/shadTooltipComponent";
import { Button } from "@/components/ui/button";
import { cn } from "@/utils/utils";
import { ButtonHTMLAttributes, useState } from "react";

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

  const handleCopy = () => {
    onCopy();
    setIsCopied(true);
    setTimeout(() => setIsCopied(false), 2000);
  };

  const handleEvaluate = (value: boolean) => {
    onEvaluate?.(evaluation === value ? null : value);
  };

  return (
    <div className="flex items-center rounded-md bg-background/95 shadow-sm scale-90">
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
                onClick={() => handleEvaluate(true)}
                className="h-6 w-6"
                data-testid="helpful-button"
              >
                <IconComponent
                  name={evaluation === true ? "ThumbUpIconCustom" : "ThumbsUp"}
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
                onClick={() => handleEvaluate(false)}
                className="h-6 w-6"
                data-testid="not-helpful-button"
              >
                <IconComponent
                  name={
                    evaluation === false ? "ThumbDownIconCustom" : "ThumbsDown"
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
