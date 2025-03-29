import { forwardRef } from "react";
import AvatarAstronautIcon from "./AvatarAstronautIcon";

export { AvatarAstronautIcon };


export default forwardRef<SVGSVGElement, React.PropsWithChildren<{ className: string }>
>((props, ref) => {
  return <AvatarAstronautIcon ref={ref} {...props} />;
}); 