import { useEffect, useId, useRef, useState, type KeyboardEvent, type ReactNode } from 'react';
import { Check } from 'lucide-react';
import { cn } from './cn';

export interface MenuItem {
  label: ReactNode;
  icon?: ReactNode;
  onSelect: () => void;
  danger?: boolean;
  disabled?: boolean;
  /** Set for a radio-style choice (e.g. theme); announced as checked/unchecked. */
  checked?: boolean;
}

/**
 * Dropdown menu (WAI-ARIA menu button): Enter/Space/ArrowDown opens, arrows
 * move, Escape closes and returns focus to the trigger.
 */
export function Menu({
  trigger,
  items,
  label,
  align = 'end',
}: {
  trigger: (props: { onClick: () => void; 'aria-haspopup': 'menu'; 'aria-expanded': boolean; 'aria-controls': string; ref: (el: HTMLButtonElement | null) => void }) => ReactNode;
  items: MenuItem[];
  label: string;
  align?: 'start' | 'end';
}) {
  const [open, setOpen] = useState(false);
  const menuId = useId();
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const itemRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const container = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    itemRefs.current.find((el) => el && !el.disabled)?.focus();
    const onDown = (event: MouseEvent) => {
      if (!container.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', onDown);
    return () => document.removeEventListener('mousedown', onDown);
  }, [open]);

  const close = () => {
    setOpen(false);
    triggerRef.current?.focus();
  };

  const onKey = (event: KeyboardEvent) => {
    const enabled = itemRefs.current.filter((el): el is HTMLButtonElement => !!el && !el.disabled);
    const index = enabled.indexOf(document.activeElement as HTMLButtonElement);
    if (event.key === 'Escape') {
      event.preventDefault();
      close();
    } else if (event.key === 'ArrowDown') {
      event.preventDefault();
      enabled[(index + 1) % enabled.length]?.focus();
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      enabled[(index - 1 + enabled.length) % enabled.length]?.focus();
    } else if (event.key === 'Tab') {
      setOpen(false);
    }
  };

  return (
    <div ref={container} className="relative inline-block">
      {trigger({
        onClick: () => setOpen((v) => !v),
        'aria-haspopup': 'menu',
        'aria-expanded': open,
        'aria-controls': menuId,
        ref: (el) => { triggerRef.current = el; },
      })}
      {open && (
        <div
          id={menuId}
          role="menu"
          aria-label={label}
          onKeyDown={onKey}
          className={cn(
            'absolute z-40 mt-1 min-w-[200px] rounded-md border border-hairline bg-canvas py-1 animate-fade-in',
            align === 'end' ? 'right-0' : 'left-0'
          )}
        >
          {items.map((item, i) => (
            <button
              key={i}
              ref={(el) => { itemRefs.current[i] = el; }}
              role={item.checked === undefined ? 'menuitem' : 'menuitemradio'}
              aria-checked={item.checked}
              type="button"
              disabled={item.disabled}
              onClick={() => {
                setOpen(false);
                item.onSelect();
              }}
              className={cn(
                'flex w-full items-center gap-2.5 px-3 py-2 text-left text-small transition-colors',
                'hover:bg-canvas-tint focus:bg-canvas-tint focus:outline-none disabled:text-disabled disabled:hover:bg-transparent',
                item.danger ? 'text-error' : 'text-ink'
              )}
            >
              {item.icon && <span className="h-4 w-4 shrink-0" aria-hidden>{item.icon}</span>}
              <span className="flex-1">{item.label}</span>
              {item.checked && <Check className="h-4 w-4 text-ink" aria-hidden />}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
