import { forwardRef } from "react";
import Avatar2IconOriginal from "./Avatar2Icon.jsx";

// Re-export the original component for compatibility
export default Avatar2IconOriginal;

export const ForwardedAvatar2Icon = forwardRef<SVGSVGElement, React.PropsWithChildren<{ className: string }>
>((props, ref) => {
  return <Avatar2IconOriginal ref={ref} {...props} />;
}); 