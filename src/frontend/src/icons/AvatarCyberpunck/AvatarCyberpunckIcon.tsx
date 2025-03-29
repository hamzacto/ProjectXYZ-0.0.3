import { forwardRef } from "react";
import AvatarCyberpunckIcon from "./AvatarCyberpunckIcon";

export { AvatarCyberpunckIcon };


export default forwardRef<SVGSVGElement, React.PropsWithChildren<{ className: string }>
>((props, ref) => {
  return <AvatarCyberpunckIcon ref={ref} {...props} />;
}); 