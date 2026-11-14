import { memo, useCallback, useMemo, useRef, useState, type AnchorHTMLAttributes } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { AlertTriangle, Check, ChevronDown, ChevronUp, Copy } from 'lucide-react';
import type { ChatMessage, Source } from '../../services/api';
import { IconButton, cn } from '../../ui';
import { CITE_PREFIX, citedNumbers, linkCitations } from './citations';
import { SourceCard } from './SourceCard';

const ABSTAIN_PREFIX = "I don't have enough information";
const REMARK_PLUGINS = [remarkGfm];

/** Renders [n] as an interactive chip linked to source card n. */
function CitationChip({ number, source, onActivate }: { number: number; source?: Source; onActivate: (n: number) => void }) {
  return (
    <button
      type="button"
      onClick={() => onActivate(number)}
      className="mx-0.5 inline-flex h-5 min-w-[20px] -translate-y-px items-center justify-center rounded-xs bg-canvas-tint px-1 align-middle text-caption font-semibold text-ink transition-colors hover:bg-ink hover:text-canvas"
      aria-label={source ? `Source ${number}: ${source.document}${source.page ? `, page ${source.page}` : ''}` : `Source ${number}`}
      title={source ? `${source.document}${source.page ? ` · p. ${source.page}` : ''}` : undefined}
    >
      {number}
    </button>
  );
}

function UserMessage({ content }: { content: string }) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[85%] whitespace-pre-wrap rounded-md bg-canvas-tint px-4 py-3 text-body-loose text-ink">
        {content}
      </div>
    </div>
  );
}

function AssistantMessage({ message }: { message: ChatMessage }) {
  const sources = (message.metadata?.sources ?? []) as Source[];
  const isError = Boolean(message.metadata?.error);
  const abstained = message.content.startsWith(ABSTAIN_PREFIX);
  const cited = useMemo(() => new Set(citedNumbers(message.content)), [message.content]);
  const markdown = useMemo(() => linkCitations(message.content), [message.content]);
  const [showSources, setShowSources] = useState(false);
  const [active, setActive] = useState<number | null>(null);
  const [copied, setCopied] = useState(false);
  const cardRefs = useRef<Record<number, HTMLLIElement | null>>({});

  const activate = useCallback((number: number) => {
    setShowSources(true);
    setActive(number);
    // Wait for the panel to render before scrolling the card into view.
    requestAnimationFrame(() =>
      cardRefs.current[number]?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
    );
  }, []);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(message.content);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard unavailable (insecure context) */
    }
  };

  // Stable across renders: a new component type each render would remount the
  // chips and drop keyboard focus right after a citation is activated.
  const markdownComponents = useMemo(() => ({
    a: ({ href, children, ...rest }: AnchorHTMLAttributes<HTMLAnchorElement>) => {
      if (href?.startsWith(CITE_PREFIX)) {
        const number = Number(href.slice(CITE_PREFIX.length));
        return <CitationChip number={number} source={sources[number - 1]} onActivate={activate} />;
      }
      return (
        <a href={href} target="_blank" rel="noopener noreferrer" {...rest}>
          {children}
        </a>
      );
    },
  }), [sources, activate]);

  return (
    <article className="group animate-rise-in" aria-label="Answer">
      {(isError || abstained) && (
        <p className={cn('mb-2 flex items-center gap-1.5 text-caption font-semibold', isError ? 'text-error' : 'text-warning')}>
          <AlertTriangle className="h-3.5 w-3.5" aria-hidden />
          {isError ? 'Something went wrong' : 'Not found in your documents'}
        </p>
      )}
      <div className="prose-answer">
        <ReactMarkdown remarkPlugins={REMARK_PLUGINS} components={markdownComponents}>
          {markdown}
        </ReactMarkdown>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-1">
        {sources.length > 0 && (
          <button
            type="button"
            onClick={() => setShowSources((v) => !v)}
            aria-expanded={showSources}
            className="inline-flex items-center gap-1.5 rounded-xs px-2 py-1 text-caption font-semibold text-ink-muted transition-colors hover:bg-ink/[0.06] hover:text-ink"
          >
            {sources.length} source{sources.length === 1 ? '' : 's'}
            {showSources ? <ChevronUp className="h-3.5 w-3.5" aria-hidden /> : <ChevronDown className="h-3.5 w-3.5" aria-hidden />}
          </button>
        )}
        <IconButton label={copied ? 'Copied' : 'Copy answer'} size="sm" onClick={copy}
          className="opacity-100 sm:opacity-0 sm:group-hover:opacity-100 sm:focus-visible:opacity-100">
          {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
        </IconButton>
      </div>

      {showSources && sources.length > 0 && (
        <ol className="mt-3 grid gap-2 lg:grid-cols-2" aria-label="Sources for this answer">
          {sources.map((source, index) => (
            <SourceCard
              key={`${source.chunk_id}-${index}`}
              ref={(el) => { cardRefs.current[index + 1] = el; }}
              source={source}
              number={index + 1}
              cited={cited.has(index + 1)}
              active={active === index + 1}
              canOpen
            />
          ))}
        </ol>
      )}
    </article>
  );
}

function MessageBubble({ message }: { message: ChatMessage }) {
  return message.role === 'user' ? <UserMessage content={message.content} /> : <AssistantMessage message={message} />;
}

export default memo(MessageBubble);
