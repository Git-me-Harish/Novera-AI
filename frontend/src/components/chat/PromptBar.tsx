import { forwardRef, useEffect, useImperativeHandle, useRef, type KeyboardEvent } from 'react';
import { ArrowUp } from 'lucide-react';
import { cn } from '../../ui';

export const MAX_QUERY_CHARS = 2000; // server-side input guardrail

export interface PromptBarHandle {
  focus: () => void;
}

/**
 * Composer: grows with its content up to a cap, Enter sends, Shift+Enter adds
 * a line (IME composition is respected), and the remaining characters are
 * shown only when they matter.
 */
export const PromptBar = forwardRef<PromptBarHandle, {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  busy?: boolean;
  placeholder?: string;
  hint?: string;
}>(function PromptBar({ value, onChange, onSubmit, busy, placeholder = 'Ask about your documents…', hint }, ref) {
  const textarea = useRef<HTMLTextAreaElement>(null);
  useImperativeHandle(ref, () => ({ focus: () => textarea.current?.focus() }));

  useEffect(() => {
    const el = textarea.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 240)}px`;
  }, [value]);

  const remaining = MAX_QUERY_CHARS - value.length;
  const canSend = value.trim().length > 0 && remaining >= 0 && !busy;

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      if (canSend) onSubmit();
    }
  };

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        if (canSend) onSubmit();
      }}
      className="rounded-md border border-field-border bg-canvas transition-colors focus-within:border-focus"
    >
      <label htmlFor="prompt" className="sr-only">Message</label>
      <textarea
        id="prompt"
        ref={textarea}
        rows={1}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={onKeyDown}
        placeholder={placeholder}
        maxLength={MAX_QUERY_CHARS + 200}
        aria-describedby="prompt-hint"
        className="block w-full resize-none bg-transparent px-4 pt-3.5 text-body-loose text-ink placeholder:text-ink-muted/80 focus:outline-none"
      />
      <div className="flex items-center justify-between gap-3 px-3 pb-3 pt-1">
        <p id="prompt-hint" className={cn('text-caption', remaining < 0 ? 'text-error' : 'text-ink-muted')}>
          {remaining < 200
            ? remaining < 0 ? `${-remaining} characters over the limit` : `${remaining} characters left`
            : hint ?? 'Enter to send · Shift+Enter for a new line'}
        </p>
        <button
          type="submit"
          disabled={!canSend}
          aria-label="Send message"
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xs bg-primary text-on-primary transition-colors hover:bg-primary-pressed disabled:bg-canvas-tint disabled:text-disabled"
        >
          <ArrowUp className="h-5 w-5" aria-hidden />
        </button>
      </div>
    </form>
  );
});
