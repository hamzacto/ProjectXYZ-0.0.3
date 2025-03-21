import { useEffect, useRef, useState } from "react";
import IconComponent from "../../components/common/genericIconComponent";
import { Button } from "../../components/ui/button";
import { Textarea } from "../../components/ui/textarea";
import {
  EDIT_TEXT_PLACEHOLDER,
  TEXT_DIALOG_SUBTITLE,
} from "../../constants/constants";
import { textModalPropsType } from "../../types/components";
import { handleKeyDown } from "../../utils/reactflowUtils";
import { classNames } from "../../utils/utils";
import BaseModal from "../baseModal";
export default function PromptTextAreaModal({
  value,
  setValue,
  children,
  disabled,
  readonly = false,
  password,
  changeVisibility,
}: textModalPropsType): JSX.Element {
  const [modalOpen, setModalOpen] = useState(false);
  const [inputValue, setInputValue] = useState(value);
  const EDIT_PROMPT_PLACE_HOLDER = `You are a research analyst specialized in market analysis. Your tasks include:

1. Analyzing market trends and competitor data
2. Providing detailed insights on industry developments
3. Answering queries about market statistics and forecasts

Example tasks you might receive:
- "Analyze the EV market growth in Europe for 2023"
- "Compare top 3 competitors in cloud computing"
- "Provide market size forecasts for AI software"

When responding:
- Use data-driven insights
- Provide clear, structured analysis
- Support conclusions with specific examples`;

  const textRef = useRef<HTMLTextAreaElement>(null);
  useEffect(() => {
    if (typeof value === "string") setInputValue(value);
  }, [value, modalOpen]);

  return (
    <BaseModal
      onChangeOpenModal={(open) => {}}
      open={modalOpen}
      setOpen={setModalOpen}
      size="x-large"
    >
      <BaseModal.Trigger disable={disabled} asChild>
        {children}
      </BaseModal.Trigger>
      <BaseModal.Header description={TEXT_DIALOG_SUBTITLE}>
        <div className="flex w-full items-start gap-3">
          <div className="flex">
            <span className="pr-2" data-testid="modal-title">
              {TEXT_DIALOG_SUBTITLE}
            </span>
            <IconComponent
              name={"FileText"}
              className="h-6 w-6 pl-1 text-primary"
              aria-hidden="true"
            />
          </div>
          {password !== undefined && (
            <div>
              <button
                onClick={() => {
                  if (changeVisibility) changeVisibility();
                }}
              >
                <IconComponent
                  name={password ? "Eye" : "EyeOff"}
                  className="h-6 w-6 cursor-pointer text-primary"
                />
              </button>
            </div>
          )}
        </div>
      </BaseModal.Header>
      <BaseModal.Content overflowHidden>
        <div className={classNames("flex h-full w-full rounded-lg border")}>
          <Textarea
            password={password}
            ref={textRef}
            className="form-input h-full w-full resize-none overflow-auto rounded-lg focus-visible:ring-1"
            value={inputValue}
            onChange={(event) => {
              setInputValue(event.target.value);
            }}
            placeholder={EDIT_PROMPT_PLACE_HOLDER}
            onKeyDown={(e) => {
              handleKeyDown(e, value, "");
            }}
            readOnly={readonly}
            id={"text-area-modal"}
            data-testid={"text-area-modal"}
          />
        </div>
      </BaseModal.Content>
      <BaseModal.Footer>
        <div className="flex w-full shrink-0 items-end justify-end">
          <Button
            data-testid="genericModalBtnSave"
            id="genericModalBtnSave"
            disabled={readonly}
            onClick={() => {
              setValue(inputValue);
              setModalOpen(false);
            }}
            type="submit"
          >
            Finish Editing
          </Button>
        </div>
      </BaseModal.Footer>
    </BaseModal>
  );
}