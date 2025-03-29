import { forwardRef } from "react";
import AvatarDetectiveIcon from "./AvatarDetectiveIcon";

export { AvatarDetectiveIcon };


export default forwardRef<SVGSVGElement, React.PropsWithChildren<{ className: string }>
>((props, ref) => {
  return <AvatarDetectiveIcon ref={ref} {...props} />;
}); 