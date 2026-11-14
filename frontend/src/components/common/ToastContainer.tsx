import { useEffect, useState } from 'react';
import { AlertCircle, AlertTriangle, CheckCircle2, Info, X } from 'lucide-react';
import { toast, type Toast, type ToastType } from '../../utils/toast';

const ICONS: Record<ToastType, JSX.Element> = {
  success: <CheckCircle2 className="h-5 w-5 text-success" aria-hidden />,
  error: <AlertCircle className="h-5 w-5 text-error" aria-hidden />,
  warning: <AlertTriangle className="h-5 w-5 text-warning" aria-hidden />,
  info: <Info className="h-5 w-5 text-link" aria-hidden />,
};

/**
 * Design.md toast: canvas, hairline border, 8px radius, no shadow; tone shows
 * only in the icon. Errors are announced assertively, everything else
 * politely. Bottom-centred on phones, bottom-right otherwise.
 */
export default function ToastContainer() {
  const [toasts, setToasts] = useState<Toast[]>([]);
  useEffect(() => toast.subscribe(setToasts), []);

  const errors = toasts.filter((t) => t.type === 'error');
  const others = toasts.filter((t) => t.type !== 'error');

  const render = (t: Toast) => (
    <div key={t.id} className="pointer-events-auto flex items-start gap-3 rounded-md border border-hairline bg-canvas px-4 py-3 animate-rise-in">
      {ICONS[t.type]}
      <p className="flex-1 text-small text-ink">{t.message}</p>
      {t.action && (
        <button
          type="button"
          onClick={() => {
            t.action?.onClick();
            toast.remove(t.id);
          }}
          className="text-small font-semibold text-link hover:underline"
        >
          {t.action.label}
        </button>
      )}
      <button type="button" onClick={() => toast.remove(t.id)} aria-label="Dismiss notification"
        className="text-ink-muted transition-colors hover:text-ink">
        <X className="h-4 w-4" aria-hidden />
      </button>
    </div>
  );

  return (
    <div className="pointer-events-none fixed inset-x-0 bottom-4 z-[70] flex flex-col items-center gap-2 px-4 md:inset-x-auto md:right-4 md:w-[380px] md:items-stretch">
      <div role="alert" aria-live="assertive" className="contents">{errors.map(render)}</div>
      <div role="status" aria-live="polite" className="contents">{others.map(render)}</div>
    </div>
  );
}
