import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from 'react';
import { Loader2 } from 'lucide-react';
import { cn } from './cn';

/*
 * Design.md buttons: every action is charcoal at a 4px radius with 10px 16px
 * padding. Only fill and border change between variants; colour never
 * arrives on a control. "danger" keeps the secondary shape and signals
 * destruction through the label colour, not a red fill.
 */
export type ButtonVariant = 'primary' | 'secondary' | 'tertiary' | 'ghost' | 'danger';
export type ButtonSize = 'sm' | 'md';

const VARIANTS: Record<ButtonVariant, string> = {
  primary: 'bg-primary text-on-primary hover:bg-primary-pressed active:bg-primary-pressed',
  secondary: 'border border-ink text-ink hover:bg-ink/[0.06] active:bg-ink/[0.1]',
  tertiary: 'bg-ink/[0.08] text-ink hover:bg-ink/[0.12] active:bg-ink/[0.16]',
  ghost: 'text-ink hover:bg-ink/[0.06] active:bg-ink/[0.1]',
  danger: 'border border-error/60 text-error hover:bg-error/[0.08] active:bg-error/[0.12]',
};

const SIZES: Record<ButtonSize, string> = {
  // 40px desktop; coarse pointers get 44px (WCAG target size).
  md: 'min-h-[40px] pointer-coarse:min-h-[44px] px-4 py-2.5 text-label',
  sm: 'min-h-[32px] pointer-coarse:min-h-[40px] px-3 py-1.5 text-label',
};

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
  leading?: ReactNode;
  trailing?: ReactNode;
  block?: boolean;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = 'primary', size = 'md', loading = false, leading, trailing, block, className, children,
    disabled, type = 'button', ...rest },
  ref
) {
  const isDisabled = disabled || loading;
  return (
    <button
      ref={ref}
      type={type}
      disabled={isDisabled}
      aria-busy={loading || undefined}
      className={cn(
        'inline-flex items-center justify-center gap-2 rounded-xs font-medium whitespace-nowrap select-none',
        'transition-colors duration-150',
        'disabled:cursor-not-allowed disabled:border disabled:border-hairline disabled:bg-canvas-soft disabled:text-disabled',
        VARIANTS[variant],
        SIZES[size],
        block && 'w-full',
        className
      )}
      {...rest}
    >
      {loading ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden /> : leading}
      {children}
      {!loading && trailing}
    </button>
  );
});

export interface IconButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  /** Required: icon-only buttons must have an accessible name. */
  label: string;
  variant?: 'ghost' | 'tertiary' | 'danger';
  size?: 'sm' | 'md';
}

export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>(function IconButton(
  { label, variant = 'ghost', size = 'md', className, children, type = 'button', ...rest },
  ref
) {
  return (
    <button
      ref={ref}
      type={type}
      aria-label={label}
      title={label}
      className={cn(
        'inline-flex items-center justify-center rounded-xs transition-colors duration-150',
        'disabled:cursor-not-allowed disabled:text-disabled disabled:hover:bg-transparent',
        size === 'md' ? 'h-9 w-9 pointer-coarse:h-11 pointer-coarse:w-11' : 'h-7 w-7 pointer-coarse:h-10 pointer-coarse:w-10',
        variant === 'ghost' && 'text-ink-muted hover:text-ink hover:bg-ink/[0.06]',
        variant === 'tertiary' && 'bg-ink/[0.08] text-ink hover:bg-ink/[0.12]',
        variant === 'danger' && 'text-ink-muted hover:text-error hover:bg-error/[0.08]',
        className
      )}
      {...rest}
    >
      {children}
    </button>
  );
});
