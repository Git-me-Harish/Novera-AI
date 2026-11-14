import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import api, { type OrganizationBranding } from '../services/api';
import { useAuth } from './AuthContext';
import { useTheme } from './ThemeContext';
import { contrastRatio, hexToChannels } from '../utils/color';
import { getFullAssetUrl } from '../utils/apiBase';

/** Dark-theme canvas (tokens.css .dark --canvas). */
const DARK_CANVAS = '#1b1917';
const DEFAULT_FAVICON = typeof document !== 'undefined'
  ? (document.getElementById('app-favicon') as HTMLLinkElement | null)?.getAttribute('href') ?? null
  : null;

/**
 * Curated organization branding. Design.md is the fixed base; an
 * organization may set only these slots. Everything else (neutrals, radii,
 * type, spacing, the absence of shadows) is not customisable, so every
 * tenant gets a consistent, accessible UI.
 */
export interface Brand {
  appName: string;
  tagline: string | null;
  logoUrl: string | null;
  logoDarkUrl: string | null;
  faviconUrl: string | null;
  /** Wordmark colour (Design.md's brand mark). */
  markColor: string | null;
  /** Primary action colour, light theme only; must reach 4.5:1 with white. */
  actionColor: string | null;
}

export const DEFAULT_BRAND: Brand = {
  appName: 'Novera',
  tagline: null,
  logoUrl: null,
  logoDarkUrl: null,
  faviconUrl: null,
  markColor: null,
  actionColor: null,
};

interface BrandContextValue {
  brand: Brand;
  refresh: () => Promise<void>;
}

const BrandContext = createContext<BrandContextValue | null>(null);

export function fromCustomization(raw: OrganizationBranding | null | undefined): Brand {
  const branding: Partial<OrganizationBranding['branding']> = raw?.branding ?? {};
  const slots = raw?.advanced?.custom_settings?.brand ?? {};
  return {
    appName: branding.app_name || DEFAULT_BRAND.appName,
    tagline: branding.app_tagline || null,
    logoUrl: branding.logo_url || null,
    logoDarkUrl: branding.logo_dark_url || null,
    faviconUrl: branding.favicon_url || null,
    markColor: typeof slots.mark_color === 'string' ? slots.mark_color : null,
    actionColor: typeof slots.action_color === 'string' ? slots.action_color : null,
  };
}

export function BrandProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const { resolved } = useTheme();
  const [brand, setBrand] = useState<Brand>(DEFAULT_BRAND);

  const refresh = useCallback(async () => {
    try {
      setBrand(fromCustomization(await api.getCurrentCustomization()));
    } catch {
      setBrand(DEFAULT_BRAND);
    }
  }, []);

  // Re-read when the signed-in organization changes.
  useEffect(() => {
    refresh();
  }, [refresh, user?.id]);

  useEffect(() => {
    const root = document.documentElement.style;
    // The wordmark is large text: 3:1 against whichever canvas it sits on.
    // A dark brand colour would vanish in the dark theme, so keep the token there.
    const mark = brand.markColor && hexToChannels(brand.markColor);
    const markReadable = brand.markColor
      ? contrastRatio(brand.markColor, resolved === 'dark' ? DARK_CANVAS : '#ffffff') >= 3
      : false;
    if (mark && markReadable) root.setProperty('--brand-mark', mark);
    else root.removeProperty('--brand-mark');

    // The action colour is a light-theme slot; dark mode flips polarity instead.
    const action = brand.actionColor && hexToChannels(brand.actionColor);
    const readable = brand.actionColor ? contrastRatio(brand.actionColor, '#ffffff') >= 4.5 : false;
    if (action && readable && resolved === 'light') {
      root.setProperty('--primary', action);
      root.setProperty('--primary-pressed', action);
    } else {
      root.removeProperty('--primary');
      root.removeProperty('--primary-pressed');
    }

    document.title = brand.appName;
    const favicon = document.getElementById('app-favicon') as HTMLLinkElement | null;
    const href = brand.faviconUrl ? getFullAssetUrl(brand.faviconUrl) : DEFAULT_FAVICON;
    if (favicon && href) favicon.setAttribute('href', href);
  }, [brand, resolved]);

  const value = useMemo(() => ({ brand, refresh }), [brand, refresh]);
  return <BrandContext.Provider value={value}>{children}</BrandContext.Provider>;
}

export function useBrand(): BrandContextValue {
  const value = useContext(BrandContext);
  if (!value) throw new Error('useBrand must be used inside BrandProvider');
  return value;
}
