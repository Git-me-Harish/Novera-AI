import type { QuotaEntry } from '../../services/api';
import { cn } from '../../ui';

export const formatBytes = (bytes: number) => {
  if (bytes < 1024) return `${bytes} B`;
  const units = ['KB', 'MB', 'GB', 'TB'];
  let value = bytes / 1024;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value >= 10 ? Math.round(value) : value.toFixed(1)} ${units[unit]}`;
};

/**
 * Used-of-limit meter. Colour carries severity only past 80% and 95%, and
 * the numbers always say it in words too.
 */
export function QuotaMeter({ label, entry, format = (n) => n.toLocaleString() }: { label: string; entry: QuotaEntry; format?: (n: number) => string }) {
  const used = entry.used ?? 0;
  const percent = entry.percent ?? 0;
  const unlimited = entry.limit === null;
  const tone = percent >= 95 ? 'bg-error' : percent >= 80 ? 'bg-warning' : 'bg-ink';

  return (
    <div>
      <div className="flex items-baseline justify-between gap-3">
        <p className="text-small font-semibold text-ink">{label}</p>
        <p className="text-small tabular-nums text-ink-muted">
          {format(used)} {unlimited ? 'used · no limit' : <>of {format(entry.limit as number)}</>}
        </p>
      </div>
      {!unlimited && (
        <>
          <div
            className="mt-2 h-2 overflow-hidden rounded-full bg-canvas-tint"
            role="meter"
            aria-label={label}
            aria-valuemin={0}
            aria-valuemax={entry.limit as number}
            aria-valuenow={used}
            aria-valuetext={`${percent}% used`}
          >
            <div className={cn('h-full rounded-full transition-[width] duration-500', tone)} style={{ width: `${Math.min(percent, 100)}%` }} />
          </div>
          {percent >= 80 && (
            <p className={cn('mt-1.5 text-caption', percent >= 95 ? 'text-error' : 'text-warning')}>
              {percent >= 100 ? 'Limit reached. New items are refused until something is removed or the limit is raised.' : `${percent}% used.`}
            </p>
          )}
        </>
      )}
    </div>
  );
}
