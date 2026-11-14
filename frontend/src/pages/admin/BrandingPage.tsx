import { useEffect, useRef, useState, type FormEvent } from 'react';
import { ArrowUp, Trash2, Upload } from 'lucide-react';
import api, { errorMessage, type BrandAssetKind, type OrganizationBranding } from '../../services/api';
import { useBrand } from '../../contexts/BrandContext';
import { getFullAssetUrl } from '../../utils/apiBase';
import { contrastRatio } from '../../utils/color';
import { Button, Card, Field, Input, Notice, PageHeader, SectionHeading, Skeleton, Textarea, cn } from '../../ui';
import { toast } from '../../utils/toast';

/** Design.md defaults, shown when a slot is empty. */
const DEFAULT_MARK = '#c74634';
const DEFAULT_ACTION = '#312d2a';
const MAX_ASSET_MB = 5;
const HEX = /^#[0-9a-f]{6}$/i;

/** Mirrors validate_brand_settings on the server. */
const SLOTS = {
  mark: { label: 'Wordmark colour', need: 3, hint: 'Your name in the sidebar and on sign-in, when no logo is set.' },
  action: { label: 'Button colour', need: 4.5, hint: 'Primary buttons, with white text. Light theme only; dark mode keeps its own.' },
} as const;

const ASSETS: { kind: BrandAssetKind; label: string; hint: string; accept: string; onDark?: boolean }[] = [
  { kind: 'light', label: 'Logo', hint: 'Replaces the wordmark. A wide PNG or SVG with a transparent background, at least 56 px tall.', accept: '.png,.svg,.webp,.jpg,.jpeg' },
  { kind: 'dark', label: 'Logo for dark mode', hint: 'Optional. Light artwork for dark backgrounds; otherwise the logo above is used.', accept: '.png,.svg,.webp', onDark: true },
  { kind: 'favicon', label: 'Browser icon', hint: 'Square, 32 × 32 px or larger. ICO, PNG or SVG.', accept: '.ico,.png,.svg' },
];

const assetUrl = (b: OrganizationBranding, kind: BrandAssetKind) =>
  kind === 'light' ? b.branding.logo_url : kind === 'dark' ? b.branding.logo_dark_url : b.branding.favicon_url;

function ColourField({ slot, value, onChange }: { slot: keyof typeof SLOTS; value: string; onChange: (v: string) => void }) {
  const { label, need, hint } = SLOTS[slot];
  const fallback = slot === 'mark' ? DEFAULT_MARK : DEFAULT_ACTION;
  const valid = value === '' || HEX.test(value);
  const ratio = HEX.test(value) ? contrastRatio(value, '#ffffff') : null;
  const passes = ratio === null || ratio >= need;
  return (
    <Field
      label={label}
      hint={valid && passes ? (ratio ? `${ratio.toFixed(2)}:1 against white · readable` : `${hint} Empty uses the default.`) : undefined}
      error={!valid ? 'Use a six-digit hex colour, like #1a2b3c.' : !passes ? `${ratio!.toFixed(2)}:1 against white. Choose a darker colour (needs ${need}:1).` : undefined}
    >
      <div className="flex items-center gap-2">
        <input
          type="color"
          value={HEX.test(value) ? value : fallback}
          onChange={(e) => onChange(e.target.value)}
          aria-label={`${label} picker`}
          className="h-11 w-12 shrink-0 cursor-pointer rounded-sm border border-field-border bg-canvas p-1"
        />
        <Input value={value} onChange={(e) => onChange(e.target.value.trim())} placeholder={fallback} maxLength={7} spellCheck={false} className="font-mono" />
        {value && <Button variant="ghost" size="sm" onClick={() => onChange('')}>Default</Button>}
      </div>
    </Field>
  );
}

function AssetSlot({ kind, label, hint, accept, onDark, url, busy, onUpload, onRemove }: (typeof ASSETS)[number] & {
  url: string | null; busy: boolean; onUpload: (file: File) => void; onRemove: () => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  return (
    <div className="flex flex-col gap-4 sm:flex-row sm:items-center">
      <div className={cn(
        'flex h-20 w-full shrink-0 items-center justify-center rounded-sm border border-hairline sm:w-48',
        onDark ? 'bg-[#1b1917]' : 'bg-[#ffffff]'
      )}>
        {url ? (
          <img src={getFullAssetUrl(url)} alt={`Current ${label.toLowerCase()}`} className={cn('max-h-14 max-w-[85%] object-contain', kind === 'favicon' && 'h-8 w-8')} />
        ) : (
          <span className={cn('text-caption', onDark ? 'text-[#b8b1aa]' : 'text-[#5f5954]')}>None</span>
        )}
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-small font-semibold text-ink">{label}</p>
        <p className="mt-0.5 text-caption text-ink-muted">{hint}</p>
        <div className="mt-2 flex gap-2">
          <Button size="sm" variant="secondary" leading={<Upload className="h-4 w-4" />} loading={busy} onClick={() => input.current?.click()}>
            {url ? 'Replace' : 'Upload'}
          </Button>
          {url && <Button size="sm" variant="ghost" leading={<Trash2 className="h-4 w-4" />} disabled={busy} onClick={onRemove}>Remove</Button>}
        </div>
        <input
          ref={input}
          type="file"
          accept={accept}
          className="sr-only"
          tabIndex={-1}
          aria-hidden
          onChange={(e) => {
            const file = e.target.files?.[0];
            e.target.value = '';
            if (!file) return;
            if (file.size > MAX_ASSET_MB * 1024 * 1024) toast.error(`Images must be under ${MAX_ASSET_MB} MB`);
            else onUpload(file);
          }}
        />
      </div>
    </div>
  );
}

export default function BrandingPage() {
  const { refresh } = useBrand();
  const [saved, setSaved] = useState<OrganizationBranding | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [name, setName] = useState('');
  const [tagline, setTagline] = useState('');
  const [mark, setMark] = useState('');
  const [action, setAction] = useState('');
  const [saving, setSaving] = useState(false);
  const [assetBusy, setAssetBusy] = useState<BrandAssetKind | null>(null);
  const [error, setError] = useState<string | null>(null);

  const adopt = (b: OrganizationBranding) => {
    setSaved(b);
    setName(b.branding.app_name ?? '');
    setTagline(b.branding.app_tagline ?? '');
    setMark(b.advanced?.custom_settings?.brand?.mark_color ?? '');
    setAction(b.advanced?.custom_settings?.brand?.action_color ?? '');
  };

  useEffect(() => {
    api.getBranding().then(adopt).catch((err) => setLoadError(errorMessage(err, 'Could not load branding')));
  }, []);

  const colourOk = (value: string, need: number) => value === '' || (HEX.test(value) && contrastRatio(value, '#ffffff') >= need);
  const valid = name.trim() !== '' && colourOk(mark, SLOTS.mark.need) && colourOk(action, SLOTS.action.need);
  const savedSlots = saved?.advanced?.custom_settings?.brand ?? {};
  const dirty = saved !== null && (
    name.trim() !== (saved.branding.app_name ?? '') ||
    tagline.trim() !== (saved.branding.app_tagline ?? '') ||
    (mark || null) !== (savedSlots.mark_color ?? null) ||
    (action || null) !== (savedSlots.action_color ?? null)
  );

  const save = async (event: FormEvent) => {
    event.preventDefault();
    if (!saved || !valid || !dirty) return;
    setSaving(true);
    setError(null);
    try {
      // custom_settings is replaced whole on the server: keep any other keys.
      const custom = { ...(saved.advanced?.custom_settings ?? {}), brand: { mark_color: mark || null, action_color: action || null } };
      adopt(await api.updateBranding({ app_name: name.trim(), app_tagline: tagline.trim(), custom_settings: custom }));
      await refresh();
      toast.success('Branding saved. Everyone sees it on their next page load.');
    } catch (err) {
      setError(errorMessage(err, 'Could not save branding'));
    } finally {
      setSaving(false);
    }
  };

  const upload = async (kind: BrandAssetKind, file: File) => {
    setAssetBusy(kind);
    try {
      const next = await api.uploadBrandAsset(file, kind);
      setSaved((prev) => (prev ? { ...prev, branding: next.branding } : next));
      await refresh();
      toast.success('Image updated');
    } catch (err) {
      toast.error(errorMessage(err, 'Upload failed'));
    } finally {
      setAssetBusy(null);
    }
  };

  const remove = async (kind: BrandAssetKind) => {
    setAssetBusy(kind);
    try {
      await api.deleteBrandAsset(kind);
      const key = kind === 'light' ? 'logo_url' : kind === 'dark' ? 'logo_dark_url' : 'favicon_url';
      setSaved((prev) => (prev ? { ...prev, branding: { ...prev.branding, [key]: null } } : prev));
      await refresh();
      toast.success('Image removed');
    } catch (err) {
      toast.error(errorMessage(err, 'Could not remove the image'));
    } finally {
      setAssetBusy(null);
    }
  };

  const previewMark = HEX.test(mark) && colourOk(mark, 3) ? mark : DEFAULT_MARK;
  const previewAction = HEX.test(action) && colourOk(action, 4.5) ? action : DEFAULT_ACTION;

  return (
    <div className="mx-auto w-full max-w-4xl px-4 py-8 lg:px-8 lg:py-section">
      <PageHeader
        eyebrow="Administration"
        title="Branding"
        description="Make the workspace yours: name, logo and two colours. Layout, type and the rest of the palette stay consistent so it is always readable."
      />

      {loadError ? (
        <div className="mt-8"><Notice tone="error">{loadError}</Notice></div>
      ) : !saved ? (
        <div className="mt-8 space-y-4"><Skeleton className="h-56" /><Skeleton className="h-64" /></div>
      ) : (
        <div className="mt-8 grid gap-6 lg:grid-cols-[1fr_18rem]">
          <div className="space-y-6">
            <form onSubmit={save} className="space-y-6" noValidate>
              <Card>
                <SectionHeading>Name</SectionHeading>
                {error && <div className="mb-4"><Notice tone="error">{error}</Notice></div>}
                <div className="space-y-4">
                  <Field label="Product name" hint="Shown in the sidebar, sign-in page and browser tab." error={name.trim() ? undefined : 'Enter a name.'}>
                    <Input value={name} onChange={(e) => setName(e.target.value)} maxLength={60} />
                  </Field>
                  <Field label="Tagline" optional hint="One line under the name on the sign-in page.">
                    <Textarea value={tagline} onChange={(e) => setTagline(e.target.value)} maxLength={140} rows={2} className="min-h-[72px]" />
                  </Field>
                </div>
              </Card>

              <Card>
                <SectionHeading description="Checked for contrast so text stays readable for everyone.">Colours</SectionHeading>
                <div className="space-y-5">
                  <ColourField slot="mark" value={mark} onChange={setMark} />
                  <ColourField slot="action" value={action} onChange={setAction} />
                </div>
              </Card>

              <div className="flex justify-end">
                <Button type="submit" loading={saving} disabled={!dirty || !valid}>Save changes</Button>
              </div>
            </form>

            <Card>
              <SectionHeading description="Saved as soon as you upload. PNG, SVG, WebP, JPG or ICO, up to 5 MB.">Images</SectionHeading>
              <div className="space-y-6">
                {ASSETS.map((asset) => (
                  <AssetSlot
                    key={asset.kind}
                    {...asset}
                    url={assetUrl(saved, asset.kind)}
                    busy={assetBusy === asset.kind}
                    onUpload={(file) => upload(asset.kind, file)}
                    onRemove={() => remove(asset.kind)}
                  />
                ))}
              </div>
            </Card>
          </div>

          <aside aria-label="Preview" className="lg:sticky lg:top-8 lg:self-start">
            <p className="mb-2 text-caption font-semibold text-ink-muted">Preview · light theme</p>
            {/* Fixed light colours: this shows what members see in the light theme. */}
            <div className="overflow-hidden rounded-md border border-hairline">
              <div className="bg-[#f1efed] px-5 py-6">
                {saved.branding.logo_url ? (
                  <img src={getFullAssetUrl(saved.branding.logo_url)} alt="" className="h-8 w-auto object-contain" />
                ) : (
                  <p className="truncate text-heading-sm font-heavy" style={{ color: previewMark }}>{name.trim() || 'Your product'}</p>
                )}
                <span className="mt-3 block h-[3px] w-10 bg-[#f0cc71]" aria-hidden />
                <p className="mt-3 line-clamp-2 text-small text-[#5f5954]">{tagline.trim() || 'Your tagline appears here.'}</p>
              </div>
              <div className="space-y-3 bg-[#ffffff] px-5 py-5">
                <div className="flex items-center gap-2 rounded-sm border border-[#8c8985] px-3 py-2 text-small text-[#5f5954]">
                  <span className="flex-1 truncate">Ask a question…</span>
                  <span className="flex h-7 w-7 items-center justify-center rounded-full text-[#ffffff]" style={{ backgroundColor: previewAction }} aria-hidden>
                    <ArrowUp className="h-4 w-4" />
                  </span>
                </div>
                <span className="inline-flex rounded-sm px-4 py-2 text-small font-semibold text-[#ffffff]" style={{ backgroundColor: previewAction }}>
                  Primary button
                </span>
              </div>
            </div>
          </aside>
        </div>
      )}
    </div>
  );
}
