import { useRef, type KeyboardEvent, type ReactNode } from 'react';
import { cn } from './cn';

export interface TabItem<T extends string> {
  id: T;
  label: ReactNode;
  count?: number | null;
}

/**
 * Light sub-navigation (Design.md product-subnav-light): the active item is
 * marked by an ink underline. Arrow keys move between tabs (roving tabindex).
 */
export function Tabs<T extends string>({
  items,
  value,
  onChange,
  label,
  className,
}: {
  items: TabItem<T>[];
  value: T;
  onChange: (id: T) => void;
  label: string;
  className?: string;
}) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);

  const onKey = (event: KeyboardEvent, index: number) => {
    const last = items.length - 1;
    const next =
      event.key === 'ArrowRight' ? (index === last ? 0 : index + 1)
      : event.key === 'ArrowLeft' ? (index === 0 ? last : index - 1)
      : event.key === 'Home' ? 0
      : event.key === 'End' ? last
      : null;
    if (next === null) return;
    event.preventDefault();
    refs.current[next]?.focus();
    onChange(items[next].id);
  };

  return (
    <div role="tablist" aria-label={label} className={cn('flex gap-1 overflow-x-auto border-b border-hairline', className)}>
      {items.map((item, index) => {
        const selected = item.id === value;
        return (
          <button
            key={item.id}
            ref={(el) => { refs.current[index] = el; }}
            role="tab"
            type="button"
            aria-selected={selected}
            tabIndex={selected ? 0 : -1}
            onClick={() => onChange(item.id)}
            onKeyDown={(event) => onKey(event, index)}
            className={cn(
              '-mb-px whitespace-nowrap border-b-2 px-3 py-2.5 text-label transition-colors',
              selected ? 'border-ink font-semibold text-ink' : 'border-transparent text-ink-muted hover:text-ink'
            )}
          >
            {item.label}
            {item.count != null && <span className="ml-1.5 text-caption text-ink-muted">{item.count}</span>}
          </button>
        );
      })}
    </div>
  );
}
