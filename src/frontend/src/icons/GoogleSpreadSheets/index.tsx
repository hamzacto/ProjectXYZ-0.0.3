import React, { forwardRef } from "react";
import { GoogleSpreadSheets } from "./GoogleSpreadSheets";

export const GoogleSpreadSheetsIcon = forwardRef<
  SVGSVGElement,
  React.PropsWithChildren<{}>
>((props, ref) => {
  return <GoogleSpreadSheets ref={ref} {...props} />;
});

