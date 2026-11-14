import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { Wordmark } from '../brand/Wordmark';
import { useBrand } from '../../contexts/BrandContext';

/**
 * Sign-in family layout: a warm hero band (wordmark, serif headline, the gold
 * rule) beside a canvas form card bounded by a hairline (Design.md
 * ex-auth-form-card). The band collapses away on small screens.
 */
export function AuthLayout({ title, subtitle, children, footer }: {
  title: ReactNode;
  subtitle?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
}) {
  const { brand } = useBrand();
  return (
    <div className="flex min-h-[100dvh] bg-canvas">
      <section className="hidden w-[44%] max-w-[640px] flex-col justify-between bg-canvas-warm p-12 xl:flex" aria-hidden>
        <Wordmark size="lg" />
        <div>
          <p className="font-serif text-display-md text-ink">
            Answers from your documents, with the evidence attached.
          </p>
          <span className="gold-rule" />
          <p className="mt-6 max-w-md text-body-loose font-book text-ink-muted">
            {brand.tagline ||
              'Every answer cites the passages it relies on, so your team can trust it and check it.'}
          </p>
        </div>
        <p className="text-caption text-ink-muted">© {new Date().getFullYear()} {brand.appName}</p>
      </section>

      <main className="flex flex-1 items-center justify-center bg-canvas-soft px-4 py-12">
        <div className="w-full max-w-[420px]">
          <Link to="/login" className="mb-8 inline-block xl:hidden" aria-label={`${brand.appName} home`}>
            <Wordmark size="lg" />
          </Link>
          <div className="rounded-md border border-hairline bg-canvas p-6 sm:p-8">
            <h1 className="text-heading-lg font-heavy">{title}</h1>
            {subtitle && <p className="mt-2 text-body text-ink-muted">{subtitle}</p>}
            <div className="mt-6">{children}</div>
          </div>
          {footer && <div className="mt-6 text-center text-small text-ink-muted">{footer}</div>}
        </div>
      </main>
    </div>
  );
}
