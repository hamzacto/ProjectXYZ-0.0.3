import React, { forwardRef } from "react";
import SvgWhatsApp from "./WhatsApp";


export const WhatsAppIcon = forwardRef<
  SVGSVGElement,
  React.PropsWithChildren<{}>
>((props, ref) => {
  return <SvgWhatsApp ref={ref} {...props} />;
});
