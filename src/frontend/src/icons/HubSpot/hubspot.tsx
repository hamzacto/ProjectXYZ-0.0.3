import React, { forwardRef } from "react";
import HubSpotIcon from "./hubspot.jsx";

export { HubSpotIcon };


export default forwardRef<SVGSVGElement, React.PropsWithChildren<{}>
>((props, ref) => {
  return <HubSpotIcon ref={ref} {...props} />;
}); 