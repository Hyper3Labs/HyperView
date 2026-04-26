"use client";

import type { ComponentProps, ReactNode } from "react";

import { cn } from "@/lib/utils";

import {
  PanelContextBar,
  type PanelContextItem,
  type PanelContextOption,
} from "./PanelContextBar";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from "./ui/dropdown-menu";
import { Button } from "./ui/button";

export type PanelToolbarItem = PanelContextItem;
export type PanelToolbarOption = PanelContextOption;

interface PanelToolbarProps {
  items?: PanelToolbarItem[];
  actions?: ReactNode;
  className?: string;
}

export function PanelToolbar({
  items = [],
  actions,
  className,
}: PanelToolbarProps) {
  return (
    <PanelContextBar
      items={items}
      rightContent={actions}
      className={className}
    />
  );
}

type PanelToolbarButtonProps = ComponentProps<typeof Button>;

export function PanelToolbarButton({
  className,
  variant = "ghost",
  size = "sm",
  ...props
}: PanelToolbarButtonProps) {
  return (
    <Button
      variant={variant}
      size={size}
      className={cn("h-6 gap-1.5 px-2 text-[12px]", className)}
      {...props}
    />
  );
}

export function PanelToolbarIconButton({
  className,
  ...props
}: PanelToolbarButtonProps) {
  return (
    <PanelToolbarButton
      className={cn(
        "w-6 px-0 text-muted-foreground hover:bg-muted/40 hover:text-foreground",
        className
      )}
      {...props}
    />
  );
}

interface PanelToolbarMenuProps {
  icon: ReactNode;
  label: string;
  title?: string;
  disabled?: boolean;
  align?: ComponentProps<typeof DropdownMenuContent>["align"];
  contentClassName?: string;
  children: ReactNode;
}

export function PanelToolbarMenu({
  icon,
  label,
  title,
  disabled = false,
  align = "end",
  contentClassName,
  children,
}: PanelToolbarMenuProps) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <PanelToolbarIconButton
          disabled={disabled}
          title={title ?? label}
          aria-label={label}
        >
          {icon}
        </PanelToolbarIconButton>
      </DropdownMenuTrigger>
      <DropdownMenuContent align={align} className={contentClassName}>
        {children}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}