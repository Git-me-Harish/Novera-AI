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

const DEFAULT_CUSTOMIZATION: Customization = {
  id: 'default',
  organization_name: 'default',
  logo_url: null,
  logo_dark_url: null,
  favicon_url: null,
  colors: {
    primary: '#0ea5e9',
    secondary: '#d946ef',
    accent: '#8b5cf6',
    background: '#ffffff',
    sidebar: '#ffffff',
    text_primary: '#111827',
    text_secondary: '#6b7280',
    button_primary: '#0ea5e9',
    button_text: '#ffffff',
  },
  typography: { 
    font_family: null,
    font_size_base: '14px',
    font_size_heading: '24px',
  },
  layout: { 
    border_radius: '8px',
    spacing_unit: '16px',
  },
  branding: {
    app_name: null,
    app_tagline: null,
  },
  custom_settings: {},
  is_active: true,
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
};

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
    console.log('Applying theme...');
    applyTheme(data);
    console.log('Theme applied!'); 
  } catch (error) {
    console.error('Failed to load customization:', error);
    // Use default customization on error
    setCustomization(DEFAULT_CUSTOMIZATION);
    applyTheme(DEFAULT_CUSTOMIZATION);
  } finally {
    setLoading(false);
  }
};

const refreshCustomization = async () => {
  console.log('refreshCustomization called');
  await loadCustomization();
};

const applyTheme = (customization: Customization) => {
  console.log('applyTheme called with:', customization);
  const root = document.documentElement;
  const colors = customization.colors;

  // Apply CSS variables for colors
  console.log('Setting color variables...');
  root.style.setProperty('--color-primary', colors.primary);
  root.style.setProperty('--color-secondary', colors.secondary);
  root.style.setProperty('--color-accent', colors.accent);
  root.style.setProperty('--color-background', colors.background);
  root.style.setProperty('--color-sidebar', colors.sidebar);
  root.style.setProperty('--color-text-primary', colors.text_primary);
  root.style.setProperty('--color-text-secondary', colors.text_secondary);
  root.style.setProperty('--color-button-primary', colors.button_primary);
  root.style.setProperty('--color-button-text', colors.button_text);

  // Apply typography settings
  if (customization.typography) {
    console.log('Applying typography:', customization.typography); 
    if (customization.typography.font_family) {
      root.style.setProperty('--font-family', customization.typography.font_family);
      document.body.style.fontFamily = customization.typography.font_family;
    }
    root.style.setProperty('--font-size-base', customization.typography.font_size_base);
    root.style.setProperty('--font-size-heading', customization.typography.font_size_heading);
  }

  // Apply layout settings
  if (customization.layout) {
    console.log('Applying layout:', customization.layout);
    root.style.setProperty('--border-radius', customization.layout.border_radius);
    root.style.setProperty('--spacing-unit', customization.layout.spacing_unit);
  }

  // Apply primary color to Tailwind
  const rgb = hexToRgb(colors.primary);
  if (rgb) {
    console.log('Applying Tailwind color shades...');
    root.style.setProperty('--color-primary-rgb', `${rgb.r}, ${rgb.g}, ${rgb.b}`);
    
    // Generate color shades for Tailwind
    generateColorShades(colors.primary, 'primary');
    generateColorShades(colors.secondary, 'secondary');
    generateColorShades(colors.accent, 'accent');
  }

  // Update favicon if provided
  if (customization.favicon_url) {
    const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';
    const fullFaviconUrl = customization.favicon_url.startsWith('http') 
      ? customization.favicon_url 
      : `${API_BASE}${customization.favicon_url}`;
    updateFavicon(fullFaviconUrl);
  }

  // Update document title if app name is provided
  if (customization.branding.app_name) {
    document.title = customization.branding.app_name;
  }
  
  console.log('Theme application complete!'); // ADD
};

  function getFullImageUrl(path: string | null): string {
    if (!path) return '';
    
    // If path already starts with http, return as is
    if (path.startsWith('http')) return path;
    
    const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';
    return `${API_BASE}${path}`;
  }

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

  // Generate shades from 50 to 900
  const shades = [
    { name: '50', lightness: 0.95 },
    { name: '100', lightness: 0.9 },
    { name: '200', lightness: 0.8 },
    { name: '300', lightness: 0.6 },
    { name: '400', lightness: 0.4 },
    { name: '500', lightness: 0 }, // Base color
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
      // Lighten
      return Math.round(value + (255 - value) * amount);
    } else {
      // Darken
      return Math.round(value * (1 + amount));
    }
  };

  return {
    r: Math.max(0, Math.min(255, adjust(rgb.r))),
    g: Math.max(0, Math.min(255, adjust(rgb.g))),
    b: Math.max(0, Math.min(255, adjust(rgb.b))),
  };
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