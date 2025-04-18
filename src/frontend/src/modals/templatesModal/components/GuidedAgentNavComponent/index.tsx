import ForwardedIconComponent from "@/components/common/genericIconComponent";
import { convertTestName } from "@/components/common/storeCardComponent/utils/convert-test-name";
import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarTrigger,
} from "@/components/ui/sidebar";
import { useIsMobile } from "../../../../hooks/use-mobile";

import { cn } from "@/utils/utils";
import { NavProps } from "../../../../types/templates/types";

interface GuidedAgentNavProps extends NavProps {
  agentName: string;
  agentAvatar: string;
}

export function GuidedAgentNavComponent({
  categories,
  currentTab,
  setCurrentTab,
  agentName,
  agentAvatar
}: GuidedAgentNavProps) {
  const isMobile = useIsMobile();

  return (
    <Sidebar collapsible={isMobile ? "icon" : "none"} className="max-w-[230px]">
      <SidebarContent className="gap-0 p-2">
        <div
          className={cn("relative flex items-center gap-2 px-2 py-3 md:px-4")}
          data-testid="modal-title"
        >
          <SidebarTrigger
            className={cn(
              "flex h-8 shrink-0 items-center rounded-md text-lg font-semibold leading-none tracking-tight text-primary outline-none ring-ring transition-[margin,opa] duration-200 ease-linear focus-visible:ring-1 md:hidden [&>svg]:size-4 [&>svg]:shrink-0",
            )}
          />
          {agentAvatar ? (
            <ForwardedIconComponent
              name={agentAvatar}
              aria-hidden="true"
              className="h-8 w-8"
            />
          ) : (
            <ForwardedIconComponent
              name="Loader2"
              aria-hidden="true"
              className="h-8 w-8 animate-spin"
            />
          )}
          <div
            className={cn(
              "text-base-semibold flex h-8 shrink-0 items-center rounded-md leading-none tracking-tight text-primary outline-none ring-ring transition-[margin,opa] duration-200 ease-linear focus-visible:ring-1 [&>svg]:size-4 [&>svg]:shrink-0",
              "group-data-[collapsible=icon]:-mt-8 group-data-[collapsible=icon]:opacity-0",
              "max-w-full overflow-hidden text-ellipsis whitespace-nowrap text-sm"
            )}
            title={agentName || "New Agent"}
          >
            {agentName ? (agentName.length > 15 ? `${agentName.substring(0, 15)}...` : agentName) : "New Agent"}
          </div>
        </div>

        {categories.map((category, index) => (
          <SidebarGroup key={index}>
            <SidebarGroupLabel
              className={`${
                index === 0
                  ? "hidden"
                  : "mb-1 text-sm font-semibold text-muted-foreground"
              }`}
            >
              {category.title}
            </SidebarGroupLabel>
            <SidebarGroupContent>
              <SidebarMenu>
                {category.items.map((link) => (
                  <SidebarMenuItem key={link.id}>
                    <SidebarMenuButton
                      onClick={() => setCurrentTab(link.id)}
                      isActive={currentTab === link.id}
                      data-testid={`side_nav_options_${link.title.toLowerCase().replace(/\s+/g, "-")}`}
                      tooltip={link.title}
                    >
                      <ForwardedIconComponent
                        name={link.icon}
                        className={`h-4 w-4 stroke-2 ${
                          currentTab === link.id
                            ? "text-accent-pink-foreground"
                            : "text-muted-foreground"
                        }`}
                      />
                      <span
                        data-testid={`category_title_${convertTestName(link.title)}`}
                      >
                        {link.title}
                      </span>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                ))}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        ))}
      </SidebarContent>
    </Sidebar>
  );
}
