"use client";

import { useStore } from "@/store/useStore";
import { Button } from "@/components/ui/button";
import { HyperViewLogo, DiscordIcon } from "./icons";
import { CENTER_PANEL_DEFS, useDockviewApi } from "./DockviewWorkspace";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import {
  ChevronDown,
  RotateCcw,
  Check,
  PanelLeft,
  PanelBottom,
  PanelRight,
  Settings,
  Search,
} from "lucide-react";
import { useState } from "react";
import { cn } from "@/lib/utils";

const PANEL_CONFIG = CENTER_PANEL_DEFS;
const DISCORD_URL = process.env.NEXT_PUBLIC_DISCORD_URL ?? "https://discord.gg/Qf2pXtY4Vf";

export function Header() {
  const { datasetInfo, leftPanelOpen, rightPanelOpen, bottomPanelOpen } = useStore();
  const dockview = useDockviewApi();
  const [datasetPickerOpen, setDatasetPickerOpen] = useState(false);

  const handlePanelToggle = (panelId: string) => {
    if (!dockview?.api) return;
    const panel = dockview.api.getPanel(panelId);
    if (panel) {
      panel.api.close();
      return;
    }
    dockview.addPanel(panelId);
  };

  // Check which panels are currently open
  const openPanels = new Set(
    PANEL_CONFIG.map((p) => p.id).filter((id) => dockview?.api?.getPanel(id))
  );

  return (
    <header className="h-7 min-h-[28px] bg-secondary border-b border-border flex items-center justify-between px-2">
        {/* Left side: Logo + View menu */}
        <div className="flex items-center gap-2">
          {/* Logo */}
          <div className="flex items-center justify-center h-6 w-6 text-primary">
            <HyperViewLogo className="h-3.5 w-3.5" />
          </div>

          {/* View dropdown */}
          {dockview && (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-6 px-2 text-[12px] leading-[16px] tracking-[-0.15px] text-muted-foreground hover:text-foreground hover:bg-muted/50"
                >
                  View
                  <ChevronDown className="ml-0.5 h-2.5 w-2.5" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="start" className="w-48">
                {/* Panel toggles - no section header, similar to Rerun */}
                {PANEL_CONFIG.map((panel) => {
                  const Icon = panel.icon;
                  const isOpen = openPanels.has(panel.id);
                  return (
                    <DropdownMenuItem
                      key={panel.id}
                      onClick={() => handlePanelToggle(panel.id)}
                      className="flex items-center justify-between h-7 text-[12px] leading-[16px]"
                    >
                      <span className="flex items-center gap-2">
                        <Icon className="h-3.5 w-3.5" />
                        {panel.label}
                      </span>
                      {isOpen && <Check className="h-3.5 w-3.5 text-primary" />}
                    </DropdownMenuItem>
                  );
                })}

                {/* Spacer */}
                <div className="h-2" />

                {/* Reset layout */}
                <DropdownMenuItem
                  onClick={() => dockview.resetLayout()}
                  className="flex items-center gap-2 h-7 text-[12px] leading-[16px]"
                >
                  <RotateCcw className="h-3.5 w-3.5" />
                  Reset Layout
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          )}
        </div>

        {/* Center: Dataset picker (VS Code style command palette trigger) */}
        <div className="flex-1 flex justify-center px-4">
          <Popover open={datasetPickerOpen} onOpenChange={setDatasetPickerOpen}>
            <PopoverTrigger asChild>
              <Button
                variant="ghost"
                size="sm"
                role="combobox"
                aria-expanded={datasetPickerOpen}
                className="h-6 min-w-[200px] max-w-[400px] px-3 text-[12px] leading-[16px] tracking-[-0.15px] text-muted-foreground hover:text-foreground bg-muted/40 hover:bg-muted/60 border border-border/50 rounded-md justify-start gap-2"
              >
                <Search className="h-3 w-3 flex-shrink-0 opacity-50" />
                <span className="truncate flex-1 text-left">
                  {datasetInfo?.name ?? "No dataset loaded"}
                </span>
              </Button>
            </PopoverTrigger>
            <PopoverContent className="w-[280px] p-0" align="center">
              <Command>
                <CommandInput
                  placeholder="Search datasets..."
                  className="h-6 text-[12px] leading-[16px]"
                />
                <CommandList>
                  <CommandEmpty className="py-4 text-xs text-center">
                    No datasets found.
                  </CommandEmpty>
                  <CommandGroup>
                    {/* Currently only show the loaded dataset */}
                    {datasetInfo && (
                      <CommandItem
                        value={datasetInfo.name}
                        onSelect={() => setDatasetPickerOpen(false)}
                        className="text-[12px] leading-[16px]"
                      >
                        <span className="flex-1 truncate">{datasetInfo.name}</span>
                        <span className="text-[10px] text-muted-foreground ml-2">
                          {datasetInfo.num_samples.toLocaleString()} samples
                        </span>
                        <Check className="h-3 w-3 ml-2 text-primary" />
                      </CommandItem>
                    )}
                  </CommandGroup>
                </CommandList>
              </Command>
            </PopoverContent>
          </Popover>
        </div>

        {/* Right side: Discord + Panel toggles + Settings */}
        <div className="flex items-center gap-0.5">
          {/* Discord link */}
          <a
            href={DISCORD_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="h-6 w-6 p-0 flex items-center justify-center rounded-sm text-muted-foreground hover:text-foreground hover:bg-muted/40 transition-colors"
            title="Join our Discord community"
          >
            <DiscordIcon className="h-3.5 w-3.5" />
          </a>

          {/* Separator */}
          <div className="w-px h-3 bg-border mx-1" />

          {/* Left panel toggle */}
          <Button
            variant="ghost"
            size="sm"
            onClick={() => dockview?.toggleZone("left")}
            className={cn(
              "h-6 w-6 p-0",
              leftPanelOpen
                ? "text-foreground bg-muted/50"
                : "text-muted-foreground hover:text-foreground hover:bg-muted/40"
            )}
          >
            <PanelLeft className="h-3.5 w-3.5" />
          </Button>

          {/* Bottom panel toggle */}
          <Button
            variant="ghost"
            size="sm"
            onClick={() => dockview?.toggleZone("bottom")}
            className={cn(
              "h-6 w-6 p-0",
              bottomPanelOpen
                ? "text-foreground bg-muted/50"
                : "text-muted-foreground hover:text-foreground hover:bg-muted/40"
            )}
          >
            <PanelBottom className="h-3.5 w-3.5" />
          </Button>

          {/* Right panel toggle */}
          <Button
            variant="ghost"
            size="sm"
            onClick={() => dockview?.toggleZone("right")}
            className={cn(
              "h-6 w-6 p-0",
              rightPanelOpen
                ? "text-foreground bg-muted/50"
                : "text-muted-foreground hover:text-foreground hover:bg-muted/40"
            )}
          >
            <PanelRight className="h-3.5 w-3.5" />
          </Button>

          {/* Separator */}
          <div className="w-px h-3 bg-border mx-1" />

          {/* Settings button */}
          <Button
            variant="ghost"
            size="sm"
            className="h-6 w-6 p-0 text-muted-foreground hover:text-foreground hover:bg-muted/40"
          >
            <Settings className="h-3.5 w-3.5" />
          </Button>
        </div>
    </header>
  );
}
