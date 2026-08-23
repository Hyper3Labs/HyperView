"use client";

import { Header } from "@/components/Header";
import { DockviewProvider, DockviewWorkspace } from "@/components/DockviewWorkspace";
import { Button } from "@/components/ui/button";
import { useHomeData } from "./useHomeData";

export default function Home() {
  const { error, isLoading, retry } = useHomeData();

  if (error) {
    return (
      <div className="h-screen flex flex-col bg-background">
        <Header />
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center">
            <div className="text-destructive text-lg mb-2">Error</div>
            <div className="text-muted-foreground">{error}</div>
            <p className="text-muted-foreground mt-4 text-sm">
              Make sure the HyperView backend is running on port 6262.
            </p>
            <Button className="mt-4" onClick={retry}>
              Retry
            </Button>
          </div>
        </div>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="h-screen flex flex-col bg-background">
        <Header />
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center">
            <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin mx-auto mb-4" />
            <div className="text-muted-foreground">Loading dataset...</div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <DockviewProvider>
      <div className="h-screen flex flex-col bg-background">
        <Header />

        {/* Main content - dockable panels */}
        <div className="flex-1 bg-background overflow-hidden">
          <DockviewWorkspace />
        </div>
      </div>
    </DockviewProvider>
  );
}
