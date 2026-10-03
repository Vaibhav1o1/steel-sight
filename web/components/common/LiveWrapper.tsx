"use client";

import { LiveProvider } from "@/lib/live";

interface LiveWrapperProps {
  children: React.ReactNode;
}

function LiveWrapper({ children }: LiveWrapperProps) {
  return <LiveProvider>{children}</LiveProvider>;
}

export { LiveWrapper };
