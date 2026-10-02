"use client";

import * as React from "react";
import { Volume2, VolumeX } from "lucide-react";
import { Button } from "@/components/ui/button";

export interface MuteToggleProps {
  className?: string;
}

const STORAGE_KEY = "billetvision_muted";

function subscribeMute(callback: () => void): () => void {
  if (typeof window === "undefined") {
    return () => {};
  }
  window.addEventListener("billetvision_mute_change", callback);
  window.addEventListener("storage", callback);
  return () => {
    window.removeEventListener("billetvision_mute_change", callback);
    window.removeEventListener("storage", callback);
  };
}

function getMuteSnapshot(): boolean {
  try {
    if (typeof window !== "undefined" && window.localStorage) {
      return window.localStorage.getItem(STORAGE_KEY) === "true";
    }
  } catch {
    // restricted localStorage
  }
  return false;
}

function getMuteServerSnapshot(): boolean {
  return false;
}

export function MuteToggle({ className }: MuteToggleProps) {
  const muted = React.useSyncExternalStore(
    subscribeMute,
    getMuteSnapshot,
    getMuteServerSnapshot,
  );

  const toggleMute = () => {
    const next = !muted;
    try {
      if (typeof window !== "undefined" && window.localStorage) {
        window.localStorage.setItem(STORAGE_KEY, next ? "true" : "false");
        window.dispatchEvent(
          new CustomEvent("billetvision_mute_change", { detail: { muted: next } }),
        );
      }
    } catch {
      // localStorage write error ignored
    }
  };

  return (
    <Button
      variant="ghost"
      size="icon"
      className={className}
      onClick={toggleMute}
      aria-label={muted ? "Unmute audio alerts" : "Mute audio alerts"}
      title={muted ? "Unmute audio alerts" : "Mute audio alerts"}
    >
      {muted ? (
        <VolumeX className="h-4 w-4 text-amber-500" />
      ) : (
        <Volume2 className="h-4 w-4 text-muted-foreground" />
      )}
    </Button>
  );
}
