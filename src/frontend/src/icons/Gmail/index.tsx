import React, { forwardRef } from "react";
import SvgGmail from "./Gmail";

export const GmailIcon = forwardRef<
  SVGSVGElement,
  React.PropsWithChildren<{}>
>((props, ref) => {
  return <SvgGmail ref={ref} {...props} />;
});