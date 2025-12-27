import { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import api from '../services/api';
import type { Customization } from '../types';

interface CustomizationContextType {
  customization: Customization | null;
  loading: boolean;
  refreshCustomization: () => Promise<void>;
  applyTheme: (customization: Customization) => void;
}

const CustomizationContext = createContext<CustomizationContextType | undefined>(undefined);

export function CustomizationProvider({ children }: { children: ReactNode }) {
  const [customization, setCustomization] = useState<Customization | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadCustomization();
  }, []);

  const loadCustomization = async () => {
    try {
      console.log('Loading customization from API...');
      const data = await api.getCurrentCustomization();
      console.log('Customization loaded:', data);
      setCustomization(data);
      applyTheme(data);
    } catch (error) {
      console.error('Failed to load customization:', error);
      // Keep existing customization or use default
    } finally {
      setLoading(false);
    }
  };

  const refreshCustomization = async () => {
    await loadCustomization();
  };

  const applyTheme = (customization: Customization) => {
    console.log('Applying comprehensive theme...');
    const root = document.documentElement;

    // Apply brand colors
    root.style.setProperty('--color-primary', customization.colors.primary);
    root.style.setProperty('--color-secondary', customization.colors.secondary);
    root.style.setProperty('--color-accent', customization.colors.accent);
    
    // Apply semantic colors
    root.style.setProperty('--color-success', customization.colors.success);
    root.style.setProperty('--color-warning', customization.colors.warning);
    root.style.setProperty('--color-error', customization.colors.error);
    root.style.setProperty('--color-info', customization.colors.info);
    
    // Apply background colors
    root.style.setProperty('--color-background', customization.colors.background);
    root.style.setProperty('--color-background-secondary', customization.colors.background_secondary);
    root.style.setProperty('--color-background-tertiary', customization.colors.background_tertiary);
    root.style.setProperty('--color-sidebar', customization.colors.sidebar);
    
    // Apply text colors
    root.style.setProperty('--color-text-primary', customization.colors.text_primary);
    root.style.setProperty('--color-text-secondary', customization.colors.text_secondary);
    
    // Apply border and shadow
    root.style.setProperty('--color-border', customization.colors.border);
    root.style.setProperty('--color-shadow', customization.colors.shadow);

    // Apply button styling
    root.style.setProperty('--button-primary-bg', customization.buttons.primary_color);
    root.style.setProperty('--button-primary-text', customization.buttons.primary_text);
    root.style.setProperty('--button-secondary-bg', customization.buttons.secondary_color);
    root.style.setProperty('--button-secondary-text', customization.buttons.secondary_text);
    root.style.setProperty('--button-border-radius', customization.buttons.border_radius);

    // Apply input styling
    root.style.setProperty('--input-border-color', customization.inputs.border_color);
    root.style.setProperty('--input-focus-color', customization.inputs.focus_color);
    root.style.setProperty('--input-border-radius', customization.inputs.border_radius);

    // Apply card styling
    root.style.setProperty('--card-background', customization.cards.background);
    root.style.setProperty('--card-border-color', customization.cards.border_color);
    root.style.setProperty('--card-border-radius', customization.cards.border_radius);
    root.style.setProperty('--card-shadow', customization.cards.shadow);

    // Apply navigation styling
    root.style.setProperty('--nav-background', customization.navigation.background);
    root.style.setProperty('--nav-text-color', customization.navigation.text_color);
    root.style.setProperty('--nav-active-color', customization.navigation.active_color);
    root.style.setProperty('--nav-hover-color', customization.navigation.hover_color);

    // Apply typography
    if (customization.typography.font_family) {
      root.style.setProperty('--font-family', customization.typography.font_family);
      document.body.style.fontFamily = customization.typography.font_family;
    }
    root.style.setProperty('--font-size-base', customization.typography.font_size_base);
    root.style.setProperty('--font-size-heading', customization.typography.font_size_heading);
    root.style.setProperty('--font-weight-normal', customization.typography.font_weight_normal);
    root.style.setProperty('--font-weight-medium', customization.typography.font_weight_medium);
    root.style.setProperty('--font-weight-bold', customization.typography.font_weight_bold);
    root.style.setProperty('--line-height-base', customization.typography.line_height_base);
    root.style.setProperty('--line-height-heading', customization.typography.line_height_heading);
    root.style.setProperty('--letter-spacing', customization.typography.letter_spacing);

    // Apply layout
    root.style.setProperty('--border-radius', customization.layout.border_radius);
    root.style.setProperty('--spacing-unit', customization.layout.spacing_unit);
    root.style.setProperty('--spacing-xs', customization.layout.spacing_xs);
    root.style.setProperty('--spacing-sm', customization.layout.spacing_sm);
    root.style.setProperty('--spacing-md', customization.layout.spacing_md);
    root.style.setProperty('--spacing-lg', customization.layout.spacing_lg);
    root.style.setProperty('--spacing-xl', customization.layout.spacing_xl);

    // Apply animations
    root.style.setProperty('--animation-speed', customization.animations.speed);
    if (!customization.animations.enabled) {
      root.style.setProperty('--animation-speed', '0ms');
    }

    // Generate color shades for Tailwind compatibility
    const rgb = hexToRgb(customization.colors.primary);
    if (rgb) {
      root.style.setProperty('--color-primary-rgb', `${rgb.r}, ${rgb.g}, ${rgb.b}`);
      generateColorShades(customization.colors.primary, 'primary');
      generateColorShades(customization.colors.secondary, 'secondary');
      generateColorShades(customization.colors.accent, 'accent');
    }

    // Apply custom CSS if provided
    if (customization.advanced.custom_css) {
      applyCustomCSS(customization.advanced.custom_css);
    }

    // Update favicon if provided
    if (customization.branding.favicon_url) {
      const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';
      const fullFaviconUrl = customization.branding.favicon_url.startsWith('http')
        ? customization.branding.favicon_url
        : `${API_BASE}${customization.branding.favicon_url}`;
      updateFavicon(fullFaviconUrl);
    }

    // Update document title if app name is provided
    if (customization.branding.app_name) {
      document.title = customization.branding.app_name;
    }

    console.log('Theme application complete!');
  };

  const value = {
    customization,
    loading,
    refreshCustomization,
    applyTheme,
  };

  return (
    <CustomizationContext.Provider value={value}>
      {children}
    </CustomizationContext.Provider>
  );
}

export function useCustomization() {
  const context = useContext(CustomizationContext);
  if (context === undefined) {
    throw new Error('useCustomization must be used within a CustomizationProvider');
  }
  return context;
}

// Helper functions
function hexToRgb(hex: string): { r: number; g: number; b: number } | null {
  const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
  return result
    ? {
        r: parseInt(result[1], 16),
        g: parseInt(result[2], 16),
        b: parseInt(result[3], 16),
      }
    : null;
}

function generateColorShades(baseColor: string, name: string) {
  const root = document.documentElement;
  const rgb = hexToRgb(baseColor);
  
  if (!rgb) return;

  const shades = [
    { name: '50', lightness: 0.95 },
    { name: '100', lightness: 0.9 },
    { name: '200', lightness: 0.8 },
    { name: '300', lightness: 0.6 },
    { name: '400', lightness: 0.4 },
    { name: '500', lightness: 0 },
    { name: '600', lightness: -0.1 },
    { name: '700', lightness: -0.2 },
    { name: '800', lightness: -0.3 },
    { name: '900', lightness: -0.4 },
  ];

  shades.forEach(shade => {
    const adjusted = adjustLightness(rgb, shade.lightness);
    root.style.setProperty(
      `--color-${name}-${shade.name}`,
      `rgb(${adjusted.r}, ${adjusted.g}, ${adjusted.b})`
    );
  });
}

function adjustLightness(
  rgb: { r: number; g: number; b: number },
  amount: number
): { r: number; g: number; b: number } {
  const adjust = (value: number) => {
    if (amount > 0) {
      return Math.round(value + (255 - value) * amount);
    } else {
      return Math.round(value * (1 + amount));
    }
  };

  return {
    r: Math.max(0, Math.min(255, adjust(rgb.r))),
    g: Math.max(0, Math.min(255, adjust(rgb.g))),
    b: Math.max(0, Math.min(255, adjust(rgb.b))),
  };
}

function applyCustomCSS(css: string) {
  const styleId = 'custom-theme-css';
  let styleElement = document.getElementById(styleId);
  
  if (!styleElement) {
    styleElement = document.createElement('style');
    styleElement.id = styleId;
    document.head.appendChild(styleElement);
  }
  
  styleElement.textContent = css;
}

function updateFavicon(faviconUrl: string) {
  const link = document.querySelector("link[rel~='icon']") as HTMLLinkElement;
  if (link) {
    link.href = faviconUrl;
  } else {
    const newLink = document.createElement('link');
    newLink.rel = 'icon';
    newLink.href = faviconUrl;
    document.head.appendChild(newLink);
  }
}