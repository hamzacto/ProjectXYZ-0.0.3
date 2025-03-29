import { forwardRef } from "react";
import AvatarBookAuthorIcon from "./AvatarBookAuthor";

export { AvatarBookAuthorIcon };


export default forwardRef<SVGSVGElement, React.PropsWithChildren<{ className: string }>
>((props, ref) => {
  return <AvatarBookAuthorIcon ref={ref} {...props} />;
}); 