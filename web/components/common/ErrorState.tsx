import * as React from "react";
import { AlertCircle, RotateCcw } from "lucide-react";
import { cn } from "cn";
import { Button } from "@/components/ui/button";

export interface ErrorStateProps {
  title?: string;
  message: string;
  hint?: string | null;
  onRetry?: () => void;
  className?: string;
}

export function ErrorState({
  title = "Something went wrong",
  message,
  hint,
  onRetry,
  className,
}: ErrorStateProps) {
  return (
    <div
      role="alert"
      className={cn(
        "flex flex-col items-center justify-center rounded-lg border border-red-200 dark:border-red-950 bg-red-50/50 dark:bg-red-950/20 p-8 text-center animate-in fade-in-50",
        className,
      )}
    >
      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-red-100 dark:bg-red-900/40 text-red-600 dark:text-red-400 mb-4">
        <AlertCircle className="h-6 w-6" />
      </div>
      <h3 className="text-base font-semibold text-red-900 dark:text-red-200">
        {title}
      </h3>
      <p className="mt-1 text-sm text-red-700 dark:text-red-300 max-w-sm">
        {message}
      </p>
      {hint ? (
        <p className="mt-2 text-xs text-muted-foreground bg-background/80 rounded px-2.5 py-1 border max-w-md font-mono">
          Hint: {hint}
        </p>
      ) : null}
      {onRetry ? (
        <Button
          variant="outline"
          size="sm"
          onClick={onRetry}
          className="mt-4 gap-2"
        >
          <RotateCcw className="h-3.5 w-3.5" />
          Try Again
        </Button>
      ) : null}
    </div>
  );
}
