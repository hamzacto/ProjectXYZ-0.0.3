import React, { forwardRef } from "react";
import SvgGoogleCalendar from "./GoogleCalendar";

export const GoogleCalendarIcon = forwardRef<SVGSVGElement, React.PropsWithChildren<{}>>((props, ref) => {
    return <SvgGoogleCalendar ref={ref} {...props} />;
});

