import { forwardRef } from "react";
import AvatarResearcherIcon from "./AvatarResearcherIcon";

export { AvatarResearcherIcon };


export default forwardRef<SVGSVGElement, React.PropsWithChildren<{ className: string }>
>((props, ref) => {
  return <AvatarResearcherIcon ref={ref} {...props} />;
}); 