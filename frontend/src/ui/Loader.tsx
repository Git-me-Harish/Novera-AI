import { useEffect, useState } from 'react';
import { cn } from './cn';

/**
 * Working indicator for AI responses: a small pixel grid that ripples, a
 * status label and the elapsed time, so a slow answer reads as progress
 * rather than a frozen screen. (Pattern inspired by beautifului.dev's
 * Loading State; implemented independently in the Novera design language.)
 */
export function PixelLoader({ label = 'Working', startedAt, className }: { label?: string; startedAt?: number; className?: string }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!startedAt) return;
    const timer = window.setInterval(() => setNow(Date.now()), 100);
    return () => window.clearInterval(timer);
  }, [startedAt]);
  const seconds = startedAt ? Math.max(0, (now - startedAt) / 1000) : null;

  return (
    <div className={cn('inline-flex items-center gap-3 text-small text-ink-muted', className)} role="status" aria-live="polite">
      <span className="grid grid-cols-3 gap-[3px]" aria-hidden>
        {Array.from({ length: 9 }).map((_, i) => (
          <span
            key={i}
            className="h-[5px] w-[5px] rounded-[1px] bg-ink animate-pulse"
            style={{ animationDelay: `${((i % 3) + Math.floor(i / 3)) * 110}ms` }}
          />
        ))}
      </span>
      <span>{label}</span>
      {seconds !== null && <span className="font-mono tabular-nums text-caption">{seconds.toFixed(1)}s</span>}
    </div>
  );
}

export function Spinner({ className, label = 'Loading' }: { className?: string; label?: string }) {
  return (
    <span role="status" aria-label={label} className={cn('inline-block h-5 w-5 animate-spin rounded-full border-2 border-hairline border-t-ink', className)} />
  );
}

/** Full-area loading state for route-level suspense. */
export function PageLoader() {
  return (
    <div className="flex min-h-[40vh] items-center justify-center">
      <Spinner />
    </div>
  );
}
