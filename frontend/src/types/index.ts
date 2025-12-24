export interface TokenStats {
  conversation_id: string;
  summary: {
    total_messages: number;
    total_tokens: number;
    cached_tokens: number;
    prompt_tokens: number;
    completion_tokens: number;
    cache_efficiency_percent: number;
    total_cost_usd: number;
    avg_tokens_per_message: number;
    avg_cost_per_message: number;
  };
  messages: MessageTokenStat[];
  pricing_info: {
    model: string;
    cached_token_price: number;
    regular_token_price: number;
    currency: string;
  };
}

export interface MessageTokenStat {
  message_id: string;
  timestamp: string;
  tokens: {
    total: number;
    cached: number;
    prompt: number;
    completion: number;
  };
  cost_usd: number;
}

// Customization Types
export interface CustomizationColors {
  primary: string;
  secondary: string;
  accent: string;
  background: string;
  sidebar: string;
  text_primary: string;
  text_secondary: string;
  button_primary: string;
  button_text: string;
}

export interface CustomizationBranding {
  app_name: string | null;
  app_tagline: string | null;
}

export interface CustomizationTypography {
  font_family: string | null;
  font_size_base: string;
  font_size_heading: string;
}

export interface CustomizationLayout {
  border_radius: string;
  spacing_unit: string;
}

export interface Customization {
  id: string;
  organization_name: string;
  logo_url: string | null;
  logo_dark_url: string | null;
  favicon_url: string | null;
  colors: CustomizationColors;
  typography: CustomizationTypography;  
  layout: CustomizationLayout; 
  branding: CustomizationBranding;
  custom_settings: Record<string, any>;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface CustomizationUpdateRequest {
  organization_name?: string;
  primary_color?: string;
  secondary_color?: string;
  accent_color?: string;
  background_color?: string;
  sidebar_color?: string;
  text_primary_color?: string;
  text_secondary_color?: string;
  button_primary_color?: string;
  button_text_color?: string;
  font_family?: string;
  font_size_base?: string; 
  font_size_heading?: string; 
  border_radius?: string;  
  spacing_unit?: string;  
  app_name?: string;
  app_tagline?: string;
  custom_settings?: Record<string, any>;
}