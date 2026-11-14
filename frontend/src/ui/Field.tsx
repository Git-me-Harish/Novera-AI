import {
  cloneElement,
  forwardRef,
  isValidElement,
  useId,
  type InputHTMLAttributes,
  type ReactElement,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from 'react';
import { cn } from './cn';

/*
 * Design.md text input: canvas fill, 1px field border, 6px radius,
 * 12px 18px padding. The border colour is the AA-adjusted field border.
 */
const CONTROL =
  'w-full rounded-sm border border-field-border bg-canvas px-4 py-2.5 text-body text-ink ' +
  'placeholder:text-ink-muted/80 transition-colors duration-150 ' +
  'hover:border-ink/60 focus:border-focus focus:outline-none focus-visible:outline-2 focus-visible:outline-focus ' +
  'disabled:cursor-not-allowed disabled:border-hairline disabled:bg-canvas-soft disabled:text-disabled ' +
  'aria-[invalid=true]:border-error';

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  function Input({ className, ...rest }, ref) {
    return <input ref={ref} className={cn(CONTROL, 'min-h-[44px]', className)} {...rest} />;
  }
);

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(
  function Textarea({ className, ...rest }, ref) {
    return <textarea ref={ref} className={cn(CONTROL, 'min-h-[96px] resize-y', className)} {...rest} />;
  }
);

export const Select = forwardRef<HTMLSelectElement, SelectHTMLAttributes<HTMLSelectElement>>(
  function Select({ className, children, ...rest }, ref) {
    return (
      <select ref={ref} className={cn(CONTROL, 'min-h-[44px] cursor-pointer pr-10', className)} {...rest}>
        {children}
      </select>
    );
  }
);

export interface FieldProps {
  label: ReactNode;
  /** The control. Field wires id, aria-describedby and aria-invalid into it. */
  children: ReactElement;
  hint?: ReactNode;
  error?: ReactNode;
  optional?: boolean;
  className?: string;
}

/** Label + control + hint/error, with the accessibility wiring done once. */
export function Field({ label, children, hint, error, optional, className }: FieldProps) {
  const generated = useId();
  const id = (isValidElement(children) && (children.props as { id?: string }).id) || generated;
  const hintId = hint ? `${id}-hint` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  const control = isValidElement(children)
    ? cloneElement(children as ReactElement<Record<string, unknown>>, {
        id,
        'aria-describedby': [hintId, errorId].filter(Boolean).join(' ') || undefined,
        'aria-invalid': error ? true : undefined,
      })
    : children;

  return (
    <div className={cn('space-y-1.5', className)}>
      <label htmlFor={id} className="block text-label font-semibold text-ink">
        {label}
        {optional && <span className="ml-1 font-normal text-ink-muted">(optional)</span>}
      </label>
      {control}
      {hint && !error && (
        <p id={hintId} className="text-caption text-ink-muted">
          {hint}
        </p>
      )}
      {error && (
        <p id={errorId} className="text-caption text-error" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
