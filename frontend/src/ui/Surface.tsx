import type { HTMLAttributes, ReactNode } from 'react';
import { cn } from './cn';

/*
 * Surfaces. Depth is a rung on the neutral ladder, never a shadow: a white
 * card on the warm app background reads as raised because it is lighter.
 * Where two surfaces share a rung, a hairline separates them.
 */
export function Card({
  className,
  tone = 'canvas',
  bordered = true,
  padded = true,
  ...rest
}: HTMLAttributes<HTMLDivElement> & { tone?: 'canvas' | 'soft' | 'warm'; bordered?: boolean; padded?: boolean }) {
  return (
    <div
      className={cn(
        'rounded-md',
        tone === 'canvas' && 'bg-canvas',
        tone === 'soft' && 'bg-canvas-soft',
        tone === 'warm' && 'bg-canvas-warm',
        bordered && 'border border-hairline',
        padded && 'p-6',
        className
      )}
      {...rest}
    />
  );
}

export type BadgeTone = 'neutral' | 'success' | 'warning' | 'error' | 'info' | 'brand';

const BADGE_TONES: Record<BadgeTone, string> = {
  neutral: 'bg-canvas-tint text-ink-muted',
  success: 'bg-success/10 text-success',
  warning: 'bg-warning/10 text-warning',
  error: 'bg-error/10 text-error',
  info: 'bg-link/10 text-link',
  brand: 'bg-ink text-canvas',
};

export function Badge({ tone = 'neutral', className, children }: { tone?: BadgeTone; className?: string; children: ReactNode }) {
  return (
    <span className={cn('inline-flex items-center gap-1 rounded-xs px-2 py-0.5 text-caption font-semibold', BADGE_TONES[tone], className)}>
      {children}
    </span>
  );
}

/** Page title in the serif display register, with the single gold rule. */
export function PageHeader({
  title,
  description,
  actions,
  eyebrow,
  rule = true,
}: {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  eyebrow?: ReactNode;
  rule?: boolean;
}) {
  return (
    <header className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
      <div className="min-w-0">
        {eyebrow && <p className="mb-2 text-label font-semibold text-ink-muted">{eyebrow}</p>}
        <h1 className="display-title">{title}</h1>
        {rule && <span className="gold-rule" aria-hidden />}
        {description && <p className="mt-4 max-w-prose text-body-loose font-book text-ink-muted">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
}

/** Section heading: the 800-weight sans register. */
export function SectionHeading({ children, description, actions }: { children: ReactNode; description?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-4 flex items-start justify-between gap-4">
      <div>
        <h2 className="text-heading-sm font-heavy">{children}</h2>
        {description && <p className="mt-1 text-small text-ink-muted">{description}</p>}
      </div>
      {actions}
    </div>
  );
}

export function EmptyState({
  icon,
  title,
  children,
  action,
  className,
}: {
  icon?: ReactNode;
  title: ReactNode;
  children?: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn('flex flex-col items-center rounded-md bg-canvas-soft px-6 py-section text-center', className)}>
      {icon && <div className="mb-4 text-ink-muted" aria-hidden>{icon}</div>}
      <p className="text-heading-sm font-heavy">{title}</p>
      {children && <p className="mt-2 max-w-prose text-body text-ink-muted">{children}</p>}
      {action && <div className="mt-6">{action}</div>}
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn('skeleton h-4', className)} aria-hidden />;
}

/** Inline error/notice panel. */
export function Notice({
  tone = 'error',
  title,
  children,
  action,
}: {
  tone?: 'error' | 'warning' | 'info' | 'success';
  title?: ReactNode;
  children: ReactNode;
  action?: ReactNode;
}) {
  const tones = {
    error: 'border-error/40 bg-error/[0.06]',
    warning: 'border-warning/40 bg-warning/[0.08]',
    info: 'border-link/30 bg-link/[0.06]',
    success: 'border-success/40 bg-success/[0.06]',
  } as const;
  return (
    <div role={tone === 'error' ? 'alert' : 'status'} className={cn('rounded-sm border px-4 py-3 text-small', tones[tone])}>
      {title && <p className="font-semibold text-ink">{title}</p>}
      <div className="text-ink">{children}</div>
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}
