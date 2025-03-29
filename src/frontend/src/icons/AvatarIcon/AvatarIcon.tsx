import { forwardRef } from "react";
import Avatar1Icon from "./Avatar1Icon";

export { Avatar1Icon };


export default forwardRef<SVGSVGElement, React.PropsWithChildren<{ className: string }>
>((props, ref) => {
  return <Avatar1Icon ref={ref} {...props} />;
}); 