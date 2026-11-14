import { Check, Minus } from 'lucide-react';
import { PASSWORD_RULES } from '../../utils/password';
import { cn } from '../../ui';

/** Live checklist under a new-password field; announced politely as it changes. */
export function PasswordRules({ password, id }: { password: string; id?: string }) {
  return (
    <ul id={id} className="mt-2 grid grid-cols-1 gap-1 sm:grid-cols-2" aria-live="polite">
      {PASSWORD_RULES.map((rule) => {
        const met = rule.test(password);
        return (
          <li key={rule.label} className={cn('flex items-center gap-1.5 text-caption', met ? 'text-success' : 'text-ink-muted')}>
            {met ? <Check className="h-3.5 w-3.5" aria-hidden /> : <Minus className="h-3.5 w-3.5" aria-hidden />}
            <span>{rule.label}<span className="sr-only">{met ? ' — met' : ' — not yet'}</span></span>
          </li>
        );
      })}
    </ul>
  );
}
