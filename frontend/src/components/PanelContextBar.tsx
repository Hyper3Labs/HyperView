"use client";

import { Check, ChevronDown } from "lucide-react";
import { type ReactNode } from "react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

export interface PanelContextOption {
  value: string;
  label: string;
  group?: string;
  disabled?: boolean;
}

interface PanelContextBaseItem {
  id: string;
  label: string;
  showLabel?: boolean;
  value: string;
  placeholder?: string;
  valueTitle?: string;
  valueClassName?: string;
}

export interface PanelContextStaticItem extends PanelContextBaseItem {
  kind?: "static";
}

export interface PanelContextSelectItem extends PanelContextBaseItem {
  kind: "select";
  options: PanelContextOption[];
  onValueChange: (value: string) => void;
  disabled?: boolean;
}

export type PanelContextItem = PanelContextStaticItem | PanelContextSelectItem;

interface PanelContextBarProps {
  items: PanelContextItem[];
  rightContent?: ReactNode;
  className?: string;
}

export function PanelContextBar({ items, rightContent, className }: PanelContextBarProps) {
  const visibleItems = items.filter((item) => item.value.trim().length > 0 || item.kind === "select");

  if (visibleItems.length === 0 && !rightContent) {
    return null;
  }

  return (
    <div
      className={cn(
        "h-6 min-h-[24px] border-b border-border bg-secondary/20 pl-1.5 pr-2",
        "flex items-center gap-1.5",
        className
      )}
    >
      <div className="min-w-0 flex-1 flex items-center gap-1.5 overflow-x-auto">
        {visibleItems.map((item, index) => {
          const valueTitle = item.valueTitle ?? item.value;
          const showLabel = item.showLabel ?? item.label.trim().length > 0;
          const selectedLabel =
            item.kind === "select"
              ? item.options.find((option) => option.value === item.value)?.label
              : undefined;
          const displayValue = selectedLabel ?? item.value ?? item.placeholder ?? "Select";

          return (
            <div key={item.id} className="flex items-center gap-1.5 min-w-0">
              {index > 0 && <span className="h-3 w-px bg-border/80 flex-shrink-0" aria-hidden="true" />}

              {showLabel && (
                <span className="text-[11px] leading-4 text-muted-foreground flex-shrink-0">
                  {item.label}
                </span>
              )}

              {item.kind === "select" ? (
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button
                      variant="ghost"
                      size="sm"
                      disabled={item.disabled || item.options.length === 0}
                      className={cn(
                        "h-[22px] max-w-[260px] justify-start gap-1.5 rounded-sm px-0.5",
                        "text-[12px] leading-[16px] font-normal text-foreground",
                        "hover:bg-muted/50",
                        item.valueClassName
                      )}
                      title={valueTitle}
                    >
                      <span className="truncate">{displayValue}</span>
                      <ChevronDown className="h-3 w-3 flex-shrink-0 text-muted-foreground" />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="start" className="min-w-[220px]">
                    {item.options.some((option) => option.group) ? (
                      <DropdownMenuRadioGroup
                        value={item.value}
                        onValueChange={(nextValue) => item.onValueChange(nextValue)}
                      >
                        {Array.from(
                          item.options.reduce((groups, option) => {
                            const groupName = option.group ?? "";
                            const existing = groups.get(groupName);
                            if (existing) {
                              existing.push(option);
                            } else {
                              groups.set(groupName, [option]);
                            }
                            return groups;
                          }, new Map<string, PanelContextOption[]>())
                        ).map(([groupName, options], groupIndex, groups) => (
                          <div key={`group-${groupName || "default"}-${groupIndex}`}>
                            {groupName && (
                              <DropdownMenuLabel>
                                {groupName}
                              </DropdownMenuLabel>
                            )}
                            {options.map((option) => (
                              <DropdownMenuRadioItem
                                key={option.value}
                                value={option.value}
                                disabled={item.disabled || option.disabled}
                              >
                                <span className="truncate">{option.label}</span>
                              </DropdownMenuRadioItem>
                            ))}
                            {groupIndex < groups.length - 1 && <DropdownMenuSeparator />}
                          </div>
                        ))}
                      </DropdownMenuRadioGroup>
                    ) : (
                      item.options.map((option) => (
                        <DropdownMenuItem
                          key={option.value}
                          onClick={() => item.onValueChange(option.value)}
                          disabled={item.disabled || option.disabled}
                        >
                          <span className="truncate flex-1">{option.label}</span>
                          {option.value === item.value && <Check className="h-3.5 w-3.5 text-primary" />}
                        </DropdownMenuItem>
                      ))
                    )}
                  </DropdownMenuContent>
                </DropdownMenu>
              ) : (
                <span
                  className={cn(
                    "truncate text-[12px] leading-[16px] text-foreground max-w-[220px]",
                    item.valueClassName
                  )}
                  title={valueTitle}
                >
                  {displayValue}
                </span>
              )}
            </div>
          );
        })}
      </div>

      {rightContent && <div className="ml-auto flex items-center gap-1 flex-shrink-0">{rightContent}</div>}
    </div>
  );
}
