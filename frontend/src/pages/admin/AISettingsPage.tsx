import { useEffect, useId, useMemo, useState, type FormEvent } from 'react';
import { AlertCircle, CheckCircle2, ListRestart, PlugZap, RotateCcw } from 'lucide-react';
import api, {
  errorMessage,
  type AIProvider,
  type AISettings,
  type AISettingsInput,
  type ModelProbe,
  type ModelTestResult,
  type ProbeFailure,
} from '../../services/api';
import { PasswordInput } from '../../components/auth/PasswordInput';
import { Badge, Button, Card, Field, Input, Modal, Notice, PageHeader, SectionHeading, Select, Skeleton, cn } from '../../ui';
import { toast } from '../../utils/toast';

const FAILURE: Record<ProbeFailure, string> = {
  unauthorized: 'The provider rejected the API key.',
  model_not_found: 'The provider does not know this model name.',
  billing_or_credits: 'The account has no credit or billing is not set up.',
  rate_limited_or_unavailable: 'The provider is busy or rate-limiting. Try again shortly.',
  rejected: 'The provider rejected the request. Check the model and endpoint.',
  blocked_or_empty: 'The model answered with nothing (it may have been filtered).',
};

/** Split a chain label like "anthropic:claude-x" for display. */
const chainLabel = (label: string, providers: AIProvider[]) => {
  const [provider, ...rest] = label.split(':');
  return { provider: providers.find((p) => p.id === provider)?.label ?? provider, model: rest.join(':') };
};

type Mode = 'platform' | 'custom';

export default function AISettingsPage() {
  const modelsListId = useId();
  const [providers, setProviders] = useState<AIProvider[]>([]);
  const [current, setCurrent] = useState<AISettings | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [mode, setMode] = useState<Mode>('platform');
  const [provider, setProvider] = useState('');
  const [model, setModel] = useState('');
  const [baseUrl, setBaseUrl] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [removeKey, setRemoveKey] = useState(false);
  const [temperature, setTemperature] = useState('');
  const [maxTokens, setMaxTokens] = useState('');
  const [fallback, setFallback] = useState(true);

  const [available, setAvailable] = useState<string[]>([]);
  const [listing, setListing] = useState(false);
  const [testing, setTesting] = useState(false);
  const [test, setTest] = useState<ModelTestResult | null>(null);
  const [saving, setSaving] = useState(false);
  const [confirmReset, setConfirmReset] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const adopt = (s: AISettings) => {
    setCurrent(s);
    setMode(s.chat ? 'custom' : 'platform');
    setProvider(s.chat?.provider ?? '');
    setModel(s.chat?.model ?? '');
    setBaseUrl(s.chat?.base_url ?? '');
    setApiKey('');
    setRemoveKey(false);
    setTemperature(s.temperature?.toString() ?? '');
    setMaxTokens(s.max_response_tokens?.toString() ?? '');
    setFallback(s.allow_platform_fallback);
    setTest(null);
  };

  useEffect(() => {
    Promise.all([api.getAIProviders(), api.getAISettings()])
      .then(([list, settings]) => {
        setProviders(list.filter((p) => p.capabilities.includes('chat')));
        adopt(settings);
      })
      .catch((err) => setLoadError(errorMessage(err, 'Could not load AI settings')));
  }, []);

  const info = providers.find((p) => p.id === provider);
  const storedSameProvider = current?.chat?.provider === provider;
  const keyOnFile = storedSameProvider && current?.chat?.api_key_set && !removeKey;
  const platformKey = storedSameProvider && current?.chat?.uses_platform_credentials;

  // Reset discovery and test results whenever the target changes.
  useEffect(() => {
    setAvailable([]);
    setTest(null);
  }, [provider, baseUrl, apiKey]);
  useEffect(() => setTest(null), [model]);

  const problems = useMemo(() => {
    const p: Record<string, string> = {};
    if (mode === 'custom') {
      if (!provider) p.provider = 'Choose a provider.';
      if (!model.trim()) p.model = 'Enter the model name.';
      if (info?.requires_base_url && !baseUrl.trim()) p.baseUrl = `${info.label} needs its endpoint URL.`;
      if (baseUrl.trim() && !/^https?:\/\/\S+$/i.test(baseUrl.trim())) p.baseUrl = 'Enter a full URL starting with https://';
      if (info?.requires_api_key && !apiKey.trim() && !keyOnFile && !platformKey) p.apiKey = `${info.label} needs an API key.`;
    }
    const t = temperature.trim();
    if (t && (Number.isNaN(Number(t)) || Number(t) < 0 || Number(t) > 2)) p.temperature = 'Between 0 and 2.';
    const m = maxTokens.trim();
    if (m && (!/^\d+$/.test(m) || Number(m) < 64 || Number(m) > 16000)) p.maxTokens = 'A whole number from 64 to 16,000.';
    return p;
  }, [mode, provider, model, info, baseUrl, apiKey, keyOnFile, platformKey, temperature, maxTokens]);

  const probe = (): ModelProbe => ({
    provider,
    model: model.trim() || undefined,
    base_url: baseUrl.trim() || null,
    api_key: apiKey.trim() || undefined,
  });

  const discover = async () => {
    setListing(true);
    try {
      const result = await api.listProviderModels(probe());
      if (!result.ok) toast.error(result.reason ? FAILURE[result.reason] : 'Could not list models');
      else if (!result.models.length) toast.info('This provider does not publish a model list. Type the model name.');
      else toast.success(`${result.models.length} models available`);
      setAvailable(result.models);
    } catch (err) {
      toast.error(errorMessage(err, 'Could not list models'));
    } finally {
      setListing(false);
    }
  };

  const runTest = async () => {
    setTesting(true);
    try {
      setTest(await api.testAIModel(probe()));
    } catch (err) {
      toast.error(errorMessage(err, 'The test could not run'));
    } finally {
      setTesting(false);
    }
  };

  const save = async (event: FormEvent) => {
    event.preventDefault();
    if (Object.keys(problems).length) return;
    setSaving(true);
    setError(null);
    const input: AISettingsInput = {
      chat: mode === 'platform' ? null : {
        provider,
        model: model.trim(),
        base_url: baseUrl.trim() || null,
        api_key: apiKey.trim() ? apiKey.trim() : removeKey ? '' : undefined,
      },
      temperature: temperature.trim() ? Number(temperature) : null,
      max_response_tokens: maxTokens.trim() ? Number(maxTokens) : null,
      allow_platform_fallback: fallback,
    };
    try {
      adopt(await api.updateAISettings(input));
      toast.success('AI settings saved. New questions use them right away.');
    } catch (err) {
      setError(errorMessage(err, 'Could not save the AI settings'));
    } finally {
      setSaving(false);
    }
  };

  const reset = async () => {
    setConfirmReset(false);
    setSaving(true);
    try {
      adopt(await api.resetAISettings());
      toast.success('Back to the platform defaults');
    } catch (err) {
      toast.error(errorMessage(err, 'Could not reset'));
    } finally {
      setSaving(false);
    }
  };

  if (loadError) {
    return (
      <div className="mx-auto w-full max-w-3xl px-4 py-section lg:px-8">
        <Notice tone="error">{loadError}</Notice>
      </div>
    );
  }

  const defaults = current?.platform_defaults;

  return (
    <div className="mx-auto w-full max-w-3xl px-4 py-8 lg:px-8 lg:py-section">
      <PageHeader
        eyebrow="Administration"
        title="AI models"
        description="Choose the model that writes your organization’s answers. Bring your own provider and key, or use the platform’s."
      />

      {!current ? (
        <div className="mt-8 space-y-4"><Skeleton className="h-64" /><Skeleton className="h-40" /></div>
      ) : (
        <form onSubmit={save} className="mt-8 space-y-6" noValidate>
          {error && <Notice tone="error">{error}</Notice>}

          <Card>
            <SectionHeading description="Answers are always grounded in your documents, whichever model writes them.">Answering model</SectionHeading>

            <div role="radiogroup" aria-label="Model source" className="grid gap-2 sm:grid-cols-2">
              {([
                ['platform', 'Platform default', defaults?.chat ? chainLabel(defaults.chat, providers).model || defaults.chat : 'Not configured'],
                ['custom', 'Choose a model', 'Any supported provider, your own key'],
              ] as const).map(([id, title, detail]) => (
                <button
                  key={id}
                  type="button"
                  role="radio"
                  aria-checked={mode === id}
                  onClick={() => setMode(id)}
                  className={cn(
                    'rounded-sm border px-4 py-3 text-left transition-colors',
                    mode === id ? 'border-ink bg-canvas-soft' : 'border-hairline hover:border-field-border'
                  )}
                >
                  <span className="block text-small font-semibold text-ink">{title}</span>
                  <span className="mt-0.5 block truncate text-caption text-ink-muted">{detail}</span>
                </button>
              ))}
            </div>

            {mode === 'platform' && !defaults?.chat && (
              <div className="mt-4"><Notice tone="warning">The platform has no default model configured. Choose a model, or questions will fail.</Notice></div>
            )}

            {mode === 'custom' && (
              <div className="mt-6 space-y-4">
                <Field label="Provider" error={problems.provider} hint={info?.note || undefined}>
                  <Select value={provider} onChange={(e) => { setProvider(e.target.value); setRemoveKey(false); }}>
                    <option value="">Choose…</option>
                    {providers.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
                  </Select>
                </Field>

                {info && (
                  <>
                    {(info.requires_base_url || baseUrl || !info.default_base_url) && (
                      <Field
                        label="Endpoint URL"
                        optional={!info.requires_base_url}
                        error={problems.baseUrl}
                        hint={info.default_base_url ? `Leave empty to use ${info.default_base_url}` : 'The provider’s API base URL. Private network addresses are refused.'}
                      >
                        <Input value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder="https://" inputMode="url" autoComplete="off" />
                      </Field>
                    )}

                    <Field
                      label="API key"
                      optional={!info.requires_api_key}
                      error={problems.apiKey}
                      hint={
                        keyOnFile
                          ? `A key (${current.chat?.api_key_hint}) is saved. Leave empty to keep it.`
                          : platformKey
                            ? 'Empty uses the platform’s key for this provider.'
                            : 'Encrypted at rest. It is never shown again.'
                      }
                    >
                      <PasswordInput value={apiKey} onChange={(e) => { setApiKey(e.target.value); if (e.target.value) setRemoveKey(false); }} autoComplete="off" spellCheck={false} />
                    </Field>
                    {storedSameProvider && current.chat?.api_key_set && !apiKey && (
                      <label className="flex items-center gap-2 text-small text-ink-muted">
                        <input type="checkbox" className="h-4 w-4 accent-[rgb(var(--primary))]" checked={removeKey} onChange={(e) => setRemoveKey(e.target.checked)} />
                        Remove the saved key
                      </label>
                    )}

                    <div className="flex flex-col gap-2 sm:flex-row sm:items-start">
                      <Field label="Model" error={problems.model} className="flex-1"
                        hint={available.length ? `${available.length} models found. Start typing to filter.` : 'The exact model id, as the provider names it.'}>
                        <Input value={model} onChange={(e) => setModel(e.target.value)} list={modelsListId} autoComplete="off" spellCheck={false} />
                      </Field>
                      <datalist id={modelsListId}>{available.map((m) => <option key={m} value={m} />)}</datalist>
                      <Button variant="secondary" className="sm:mt-7" leading={<ListRestart className="h-4 w-4" />} loading={listing} onClick={discover}>
                        Find models
                      </Button>
                    </div>

                    <div className="flex flex-wrap items-center gap-3">
                      <Button variant="secondary" leading={<PlugZap className="h-4 w-4" />} loading={testing} onClick={runTest}
                        disabled={!provider || !model.trim() || Boolean(problems.baseUrl)}>
                        Test connection
                      </Button>
                      {test && (
                        <p role="status" className={cn('inline-flex items-center gap-1.5 text-small', test.ok ? 'text-success' : 'text-error')}>
                          {test.ok ? <CheckCircle2 className="h-4 w-4" aria-hidden /> : <AlertCircle className="h-4 w-4" aria-hidden />}
                          {test.ok ? `Working · answered in ${((test.latency_ms ?? 0) / 1000).toFixed(1)} s` : test.reason ? FAILURE[test.reason] : 'The test failed.'}
                        </p>
                      )}
                    </div>
                  </>
                )}
              </div>
            )}
          </Card>

          <Card>
            <SectionHeading description="Leave empty to follow the platform defaults.">Answer style</SectionHeading>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Temperature" optional error={problems.temperature}
                hint={`Lower is more literal. Platform default: ${defaults?.temperature ?? '—'}.`}>
                <Input value={temperature} onChange={(e) => setTemperature(e.target.value)} inputMode="decimal" placeholder={String(defaults?.temperature ?? '')} />
              </Field>
              <Field label="Longest answer (tokens)" optional error={problems.maxTokens}
                hint={`About ¾ of a word each. Platform default: ${defaults?.max_response_tokens?.toLocaleString() ?? '—'}.`}>
                <Input value={maxTokens} onChange={(e) => setMaxTokens(e.target.value)} inputMode="numeric" placeholder={String(defaults?.max_response_tokens ?? '')} />
              </Field>
            </div>
            <label className="mt-6 flex items-start gap-3 border-t border-hairline pt-6 text-small text-ink">
              <input type="checkbox" className="mt-0.5 h-4 w-4 accent-[rgb(var(--primary))]" checked={fallback} onChange={(e) => setFallback(e.target.checked)} />
              <span>
                <span className="font-semibold">Fall back to the platform model</span>
                <span className="block text-ink-muted">If your model fails or is out of credit, answer with the platform’s instead of showing an error.</span>
              </span>
            </label>
          </Card>

          {current.effective_chat_models.length > 0 && (
            <Card tone="soft">
              <SectionHeading description="Saved settings. Each model is tried in turn until one answers.">Currently answering</SectionHeading>
              <ol className="space-y-2">
                {current.effective_chat_models.map((label, i) => {
                  const { provider: p, model: m } = chainLabel(label, providers);
                  return (
                    <li key={label} className="flex items-center gap-3 text-small">
                      <span className="w-5 text-right tabular-nums text-ink-muted">{i + 1}.</span>
                      <span className="font-semibold text-ink">{m}</span>
                      <Badge>{p}</Badge>
                    </li>
                  );
                })}
              </ol>
            </Card>
          )}

          <Card tone="soft" bordered={false}>
            <SectionHeading description="Shared by every organization on this server. Changing them means re-indexing all documents.">Platform-managed</SectionHeading>
            <dl className="grid gap-4 text-small sm:grid-cols-3">
              <div><dt className="text-ink-muted">Embedding model</dt><dd className="mt-0.5 break-all font-semibold text-ink">{defaults?.embedding ?? '—'}</dd></div>
              <div><dt className="text-ink-muted">Dimensions</dt><dd className="mt-0.5 font-semibold text-ink">{defaults?.embedding_dimensions}</dd></div>
              <div><dt className="text-ink-muted">Re-ranker</dt><dd className="mt-0.5 break-all font-semibold text-ink">{defaults?.rerank}</dd></div>
            </dl>
          </Card>

          <div className="flex flex-col-reverse gap-2 border-t border-hairline pt-6 sm:flex-row sm:justify-between">
            <Button variant="ghost" leading={<RotateCcw className="h-4 w-4" />} onClick={() => setConfirmReset(true)} disabled={saving || (!current.chat && current.temperature === null && current.max_response_tokens === null && current.allow_platform_fallback)}>
              Reset to platform defaults
            </Button>
            <Button type="submit" loading={saving}>Save</Button>
          </div>
        </form>
      )}

      <Modal
        open={confirmReset}
        onClose={() => setConfirmReset(false)}
        size="sm"
        title="Reset to platform defaults?"
        description="Your model choice, saved API key and answer style are removed. The platform’s model answers from now on."
        footer={
          <>
            <Button variant="ghost" onClick={() => setConfirmReset(false)}>Cancel</Button>
            <Button variant="danger" onClick={reset}>Reset</Button>
          </>
        }
      />
    </div>
  );
}
