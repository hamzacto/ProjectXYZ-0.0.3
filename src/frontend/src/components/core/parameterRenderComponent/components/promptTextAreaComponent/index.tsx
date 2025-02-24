import { GRADIENT_CLASS } from "@/constants/constants";
import ComponentTextModal from "@/modals/textAreaModal";
import { useRef, useState } from "react";
import { cn } from "../../../../../utils/utils";
import IconComponent from "../../../../common/genericIconComponent";
import { Textarea } from "../../../../ui/textarea";
import { getPlaceholder } from "../../helpers/get-placeholder-disabled";
import { InputProps, TextAreaComponentType } from "../../types";
import { getIconName } from "../inputComponent/components/helpers/get-icon-name";
import PromptTextAreaModal from "@/modals/promptTextAreaModal";

const inputClasses = {
    base: ({ isFocused, password }: { isFocused: boolean; password: boolean }) =>
      `w-full ${isFocused ? "" : "pr-3"} ${password ? "pr-16" : ""}`,
    editNode: "input-edit-node",
    normal: ({ isFocused }: { isFocused: boolean }) =>
      `primary-input ${isFocused ? "text-primary" : "text-muted-foreground"}`,
    disabled: "disabled-state",
    password: "password",
  };

const externalLinkIconClasses = {
  gradient: ({
    disabled,
    editNode,
    password,
  }: {
    disabled: boolean;
    editNode: boolean;
    password: boolean;
  }) =>
    disabled || password
      ? ""
      : editNode
        ? "gradient-fade-input-edit-node"
        : "gradient-fade-input",
  background: ({
    disabled,
    editNode,
  }: {
    disabled: boolean;
    editNode: boolean;
  }) =>
    disabled
      ? ""
      : editNode
        ? "background-fade-input-edit-node"
        : "background-fade-input",
  icon: "icons-parameters-comp absolute right-3 h-4 w-4 shrink-0",
  editNodeTop: "top-[-1.4rem] h-5",
  normalTop: "top-[-2.1rem] h-7",
  iconTop: "top-[-1.7rem]",
};

export default function PromptTextAreaComponent({
  value,
  disabled,
  handleOnNewValue,
  editNode = false,
  id = "",
  updateVisibility,
  password,
  placeholder,
  isToolMode = false,
}: InputProps<string, TextAreaComponentType>): JSX.Element {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [isFocused, setIsFocused] = useState(false);
  const [passwordVisible, setPasswordVisible] = useState(false);

  const getTextAreaClassName = () => {
    return cn(
      inputClasses.base({ isFocused, password: password! }),
      editNode ? inputClasses.editNode : inputClasses.normal({ isFocused }),
      disabled && inputClasses.disabled,
      password && !passwordVisible && "text-clip",
      isFocused && "pr-10",
      "min-h-[200px] max-h-[200px] resize-none",
    );
  };

  const handleTextAreaChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    handleOnNewValue({ value: e.target.value });
  };

  const renderIcon = () => (
    <div>
      {!disabled && (
        <div
          className={cn(
            externalLinkIconClasses.gradient({
              disabled,
              editNode,
              password: password!,
            }),
            editNode
              ? externalLinkIconClasses.editNodeTop
              : externalLinkIconClasses.normalTop,
          )}
          style={{
            pointerEvents: "none",
            background: isFocused
              ? undefined
              : disabled
                ? "bg-background"
                : GRADIENT_CLASS,
          }}
          aria-hidden="true"
        />
      )}

      <IconComponent
        dataTestId={`button_open_text_area_modal_${id}${editNode ? "_advanced" : ""}`}
        name={getIconName(disabled, "", "", false, isToolMode) || "Scan"}
        className={cn(
          "cursor-pointer bg-background",
          externalLinkIconClasses.icon,
          editNode
            ? externalLinkIconClasses.editNodeTop
            : externalLinkIconClasses.iconTop,
          disabled
            ? "bg-muted text-placeholder-foreground"
            : "bg-background text-foreground",
        )}
      />
    </div>
  );

  return (
    <div className={cn("w-full", disabled && "pointer-events-none")}>
      <Textarea
        onFocus={() => setIsFocused(true)}
        onBlur={() => setIsFocused(false)}
        id={id}
        data-testid={id}
        value={disabled ? "" : value}
        onChange={handleTextAreaChange}
        disabled={disabled}
        className={cn(
          getTextAreaClassName(),
          "form-input h-full w-full resize-none overflow-auto rounded-lg focus-visible:ring-1"
        )}
        placeholder={getPlaceholder(disabled, placeholder)}
        aria-label={disabled ? value : undefined}
        ref={textareaRef}
      />

      <PromptTextAreaModal
        changeVisibility={updateVisibility}
        value={value}
        setValue={(newValue) => handleOnNewValue({ value: newValue })}
        disabled={disabled}
      >
        <div className="relative w-full">{renderIcon()}</div>
      </PromptTextAreaModal>
      
      {password && !isFocused && (
        <div
          onClick={() => {
            setPasswordVisible(!passwordVisible);
          }}
        >
          <IconComponent
            name={passwordVisible ? "eye" : "eye-off"}
            className={cn(
              externalLinkIconClasses.icon,
              editNode ? "top-[5px]" : "top-[13px]",
              disabled
                ? "text-placeholder"
                : "text-placeholder-foreground hover:text-foreground",
              "right-10",
            )}
          />
        </div>
      )}
    </div>
  );
}