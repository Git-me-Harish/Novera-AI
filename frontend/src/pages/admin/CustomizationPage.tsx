import { useState, useEffect } from 'react';
import { 
  Palette, 
  Upload, 
  Save, 
  RotateCcw, 
  Eye, 
  X,
  ChevronDown,
  ChevronUp
} from 'lucide-react';
import api from '../../services/api';
import { useCustomization } from '../../contexts/CustomizationContext';
import { toast } from '../../utils/toast';
import type { CustomizationUpdateRequest } from '../../types';
import ImagePreviewModal from '../../components/admin/ImagePreviewModal';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

function getFullImageUrl(path: string | null): string {
  if (!path) return '';
  if (path.startsWith('http')) return path;
  return `${API_BASE}${path}`;
}

export default function CustomizationPage() {
  const { refreshCustomization } = useCustomization();
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [showPreview, setShowPreview] = useState(false);

  // Mobile accordion states
  const [expandedSections, setExpandedSections] = useState({
    branding: true,
    logos: false,
    colors: false,
    typography: false,
    layout: false,
  });

  // Form state
  const organizationName = 'default';
  const [colors, setColors] = useState({
    primary: '#0ea5e9',
    secondary: '#d946ef',
    accent: '#8b5cf6',
    background: '#ffffff',
    sidebar: '#ffffff',
    text_primary: '#111827',
    text_secondary: '#6b7280',
    button_primary: '#0ea5e9',
    button_text: '#ffffff',
  });

  const [branding, setBranding] = useState({
    app_name: '',
    app_tagline: '',
  });

  const [logos, setLogos] = useState({
    light: null as string | null,
    dark: null as string | null,
    favicon: null as string | null,
  });

  const [typography, setTypography] = useState({
    font_family: '',
    font_size_base: '14px',
    font_size_heading: '24px',
  });

  const [layout, setLayout] = useState({
    border_radius: '8px',
    spacing_unit: '16px',
  });

  const [uploadingLogo, setUploadingLogo] = useState<string | null>(null);

  const [previewModal, setPreviewModal] = useState({
    isOpen: false,
    file: null as File | null,
    previewUrl: null as string | null,
    logoType: 'light' as 'light' | 'dark' | 'favicon',
  });

  useEffect(() => {
    loadCustomization();
  }, []);

  const loadCustomization = async () => {
    setLoading(true);
    try {
      const data = await api.getAdminCustomization(organizationName);
      
      setColors(data.colors);
      setBranding({
        app_name: data.branding.app_name || '',
        app_tagline: data.branding.app_tagline || '',
      });
      setLogos({
        light: data.logo_url ? getFullImageUrl(data.logo_url) : null,
        dark: data.logo_dark_url ? getFullImageUrl(data.logo_dark_url) : null,
        favicon: data.favicon_url ? getFullImageUrl(data.favicon_url) : null,
      });
      
      if (data.typography) {
        setTypography({
          font_family: data.typography.font_family || '',
          font_size_base: data.typography.font_size_base || '14px',
          font_size_heading: data.typography.font_size_heading || '24px',
        });
      }
      
      if (data.layout) {
        setLayout({
          border_radius: data.layout.border_radius || '8px',
          spacing_unit: data.layout.spacing_unit || '16px',
        });
      }
    } catch (error: any) {
      toast.error('Failed to load customization');
      console.error('Load customization error:', error);
    } finally {
      setLoading(false);
    }
  };

  const toggleSection = (section: keyof typeof expandedSections) => {
    setExpandedSections(prev => ({
      ...prev,
      [section]: !prev[section]
    }));
  };

  const handleColorChange = (colorKey: string, value: string) => {
    setColors(prev => ({ ...prev, [colorKey]: value }));
  };

  const handleBrandingChange = (field: string, value: string) => {
    setBranding(prev => ({ ...prev, [field]: value }));
  };

  const handleTypographyChange = (field: string, value: string) => {
    setTypography(prev => ({ ...prev, [field]: value }));
  };

  const handleLayoutChange = (field: string, value: string) => {
    setLayout(prev => ({ ...prev, [field]: value }));
  };

  const handleLogoUpload = async (
    event: React.ChangeEvent<HTMLInputElement>,
    logoType: 'light' | 'dark' | 'favicon'
  ) => {
    const file = event.target.files?.[0];
    if (!file) return;

    if (file.size > 5 * 1024 * 1024) {
      toast.error('File size must be less than 5MB');
      event.target.value = '';
      return;
    }

    const validTypes = ['image/png', 'image/jpeg', 'image/svg+xml', 'image/x-icon'];
    if (!validTypes.includes(file.type)) {
      toast.error('Invalid file type. Use PNG, JPG, SVG, or ICO');
      event.target.value = '';
      return;
    }

    const previewUrl = URL.createObjectURL(file);

    setPreviewModal({
      isOpen: true,
      file,
      previewUrl,
      logoType,
    });

    event.target.value = '';
  };

  const confirmLogoUpload = async () => {
    const { file, logoType } = previewModal;
    
    if (!file) return;

    closePreviewModal();

    setUploadingLogo(logoType);
    try {
      const response = await api.uploadLogo(file, logoType, organizationName);
      const fullUrl = getFullImageUrl(response.url);
      setLogos(prev => ({ ...prev, [logoType]: fullUrl }));
      toast.success(`${logoType} logo uploaded successfully`);
    } catch (error: any) {
      toast.error(`Failed to upload ${logoType} logo`);
      console.error(error);
    } finally {
      setUploadingLogo(null);
    }
  };

  const closePreviewModal = () => {
    if (previewModal.previewUrl) {
      URL.revokeObjectURL(previewModal.previewUrl);
    }
    
    setPreviewModal({
      isOpen: false,
      file: null,
      previewUrl: null,
      logoType: 'light',
    });
  };

  const handleLogoDelete = async (logoType: 'light' | 'dark' | 'favicon') => {
    if (!confirm(`Are you sure you want to delete the ${logoType} logo?`)) {
      return;
    }

    try {
      await api.deleteLogo(logoType, organizationName);
      setLogos(prev => ({ ...prev, [logoType]: null }));
      toast.success(`${logoType} logo deleted`);
    } catch (error: any) {
      toast.error(`Failed to delete ${logoType} logo`);
      console.error(error);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const updateData: CustomizationUpdateRequest = {
        primary_color: colors.primary,
        secondary_color: colors.secondary,
        accent_color: colors.accent,
        background_color: colors.background,
        sidebar_color: colors.sidebar,
        text_primary_color: colors.text_primary,
        text_secondary_color: colors.text_secondary,
        button_primary_color: colors.button_primary,
        button_text_color: colors.button_text,
        font_family: typography.font_family || undefined,
        font_size_base: typography.font_size_base,
        font_size_heading: typography.font_size_heading,
        border_radius: layout.border_radius,
        spacing_unit: layout.spacing_unit,
        app_name: branding.app_name || undefined,
        app_tagline: branding.app_tagline || undefined,
      };

      await api.updateCustomization(updateData, organizationName);
      await refreshCustomization();
      
      toast.success('Customization saved! Page will reload to apply changes...');
      
      setTimeout(() => {
        window.location.reload();
      }, 1500);
    } catch (error: any) {
      toast.error('Failed to save customization');
      console.error(error);
    } finally {
      setSaving(false);
    }
  };

  const handleReset = async () => {
    if (!confirm('Are you sure you want to reset all customization to defaults?')) {
      return;
    }

    try {
      await api.resetCustomization(organizationName);
      await loadCustomization();
      await refreshCustomization();
      toast.success('Customization reset to defaults');
      
      setTimeout(() => {
        window.location.reload();
      }, 1000);
    } catch (error: any) {
      toast.error('Failed to reset customization');
      console.error(error);
    }
  };

  const togglePreview = () => {
    setShowPreview(!showPreview);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600"></div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto bg-gray-50 scroll-smooth-touch">
      <div className="max-w-7xl mx-auto px-3 sm:px-6 py-4 sm:py-8">
        {/* Header */}
        <div className="mb-6 sm:mb-8">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 sm:gap-0">
            <div>
              <div className="flex items-center gap-2 mb-2">
                <Palette className="w-6 h-6 sm:w-8 sm:h-8 text-primary-600" />
                <h1 className="text-2xl sm:text-3xl font-bold text-gray-900">Customization</h1>
              </div>
              <p className="text-sm sm:text-base text-gray-600">Customize your organization's branding and theme</p>
            </div>

            <div className="flex flex-col sm:flex-row gap-2 sm:gap-3">
              <button
                onClick={togglePreview}
                className="flex items-center justify-center gap-2 px-4 py-2.5 border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors text-sm sm:text-base font-medium min-touch-target"
              >
                <Eye className="w-4 h-4" />
                {showPreview ? 'Hide Preview' : 'Show Preview'}
              </button>
              <button
                onClick={handleReset}
                className="flex items-center justify-center gap-2 px-4 py-2.5 border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors text-orange-600 text-sm sm:text-base font-medium min-touch-target"
              >
                <RotateCcw className="w-4 h-4" />
                <span className="hidden xs:inline">Reset to Defaults</span>
                <span className="xs:hidden">Reset</span>
              </button>
              <button
                onClick={handleSave}
                disabled={saving}
                className="flex items-center justify-center gap-2 px-4 sm:px-6 py-2.5 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors disabled:opacity-50 text-sm sm:text-base font-medium min-touch-target"
              >
                <Save className="w-4 h-4" />
                {saving ? 'Saving...' : 'Save Changes'}
              </button>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 sm:gap-6">
          {/* Main Settings */}
          <div className="lg:col-span-2 space-y-3 sm:space-y-6">
            {/* Branding Section */}
            <AccordionSection
              title="Branding"
              isExpanded={expandedSections.branding}
              onToggle={() => toggleSection('branding')}
            >
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Application Name
                  </label>
                  <input
                    type="text"
                    value={branding.app_name}
                    onChange={(e) => handleBrandingChange('app_name', e.target.value)}
                    placeholder="Novera AI"
                    className="w-full px-3 sm:px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent text-sm sm:text-base"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Tagline
                  </label>
                  <input
                    type="text"
                    value={branding.app_tagline}
                    onChange={(e) => handleBrandingChange('app_tagline', e.target.value)}
                    placeholder="AI-Powered Knowledge Assistant"
                    className="w-full px-3 sm:px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent text-sm sm:text-base"
                  />
                </div>
              </div>
            </AccordionSection>

            {/* Logo Upload Section */}
            <AccordionSection
              title="Logos"
              isExpanded={expandedSections.logos}
              onToggle={() => toggleSection('logos')}
            >
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 sm:gap-4">
                <LogoUploadCard
                  title="Light Mode Logo"
                  logoUrl={logos.light}
                  uploading={uploadingLogo === 'light'}
                  onUpload={(e) => handleLogoUpload(e, 'light')}
                  onDelete={() => handleLogoDelete('light')}
                />
                
                <LogoUploadCard
                  title="Dark Mode Logo"
                  logoUrl={logos.dark}
                  uploading={uploadingLogo === 'dark'}
                  onUpload={(e) => handleLogoUpload(e, 'dark')}
                  onDelete={() => handleLogoDelete('dark')}
                />
                
                <LogoUploadCard
                  title="Favicon"
                  logoUrl={logos.favicon}
                  uploading={uploadingLogo === 'favicon'}
                  onUpload={(e) => handleLogoUpload(e, 'favicon')}
                  onDelete={() => handleLogoDelete('favicon')}
                />
              </div>
            </AccordionSection>

            {/* Color Customization */}
            <AccordionSection
              title="Colors"
              isExpanded={expandedSections.colors}
              onToggle={() => toggleSection('colors')}
            >
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 sm:gap-6">
                <ColorPicker
                  label="Primary Color"
                  value={colors.primary}
                  onChange={(value) => handleColorChange('primary', value)}
                  description="Main brand color"
                />
                
                <ColorPicker
                  label="Secondary Color"
                  value={colors.secondary}
                  onChange={(value) => handleColorChange('secondary', value)}
                  description="Secondary accent color"
                />
                
                <ColorPicker
                  label="Accent Color"
                  value={colors.accent}
                  onChange={(value) => handleColorChange('accent', value)}
                  description="Highlight color"
                />
                
                <ColorPicker
                  label="Background Color"
                  value={colors.background}
                  onChange={(value) => handleColorChange('background', value)}
                  description="Main background"
                />
                
                <ColorPicker
                  label="Sidebar Color"
                  value={colors.sidebar}
                  onChange={(value) => handleColorChange('sidebar', value)}
                  description="Sidebar background"
                />
                
                <ColorPicker
                  label="Primary Text"
                  value={colors.text_primary}
                  onChange={(value) => handleColorChange('text_primary', value)}
                  description="Main text color"
                />
                
                <ColorPicker
                  label="Secondary Text"
                  value={colors.text_secondary}
                  onChange={(value) => handleColorChange('text_secondary', value)}
                  description="Muted text color"
                />
                
                <ColorPicker
                  label="Button Text"
                  value={colors.button_text}
                  onChange={(value) => handleColorChange('button_text', value)}
                  description="Text on buttons"
                />
              </div>
            </AccordionSection>

            {/* Typography Section */}
            <AccordionSection
              title="Typography"
              isExpanded={expandedSections.typography}
              onToggle={() => toggleSection('typography')}
            >
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Font Family
                  </label>
                  <select
                    value={typography.font_family}
                    onChange={(e) => handleTypographyChange('font_family', e.target.value)}
                    className="w-full px-3 sm:px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent text-sm sm:text-base"
                  >
                    <option value="">System Default</option>
                    <option value="Inter">Inter</option>
                    <option value="Roboto">Roboto</option>
                    <option value="Poppins">Poppins</option>
                    <option value="Open Sans">Open Sans</option>
                    <option value="Lato">Lato</option>
                    <option value="Montserrat">Montserrat</option>
                  </select>
                  <p className="text-xs text-gray-500 mt-1">
                    Choose a font for your application
                  </p>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      Base Font Size
                    </label>
                    <input
                      type="text"
                      value={typography.font_size_base}
                      onChange={(e) => handleTypographyChange('font_size_base', e.target.value)}
                      placeholder="14px"
                      className="w-full px-3 sm:px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent text-sm sm:text-base"
                    />
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">
                      Heading Font Size
                    </label>
                    <input
                      type="text"
                      value={typography.font_size_heading}
                      onChange={(e) => handleTypographyChange('font_size_heading', e.target.value)}
                      placeholder="24px"
                      className="w-full px-3 sm:px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent text-sm sm:text-base"
                    />
                  </div>
                </div>
              </div>
            </AccordionSection>

            {/* Layout Section */}
            <AccordionSection
              title="Layout"
              isExpanded={expandedSections.layout}
              onToggle={() => toggleSection('layout')}
            >
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Border Radius
                  </label>
                  <select
                    value={layout.border_radius}
                    onChange={(e) => handleLayoutChange('border_radius', e.target.value)}
                    className="w-full px-3 sm:px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent text-sm sm:text-base"
                  >
                    <option value="0px">None (0px)</option>
                    <option value="4px">Small (4px)</option>
                    <option value="8px">Medium (8px)</option>
                    <option value="12px">Large (12px)</option>
                    <option value="16px">Extra Large (16px)</option>
                    <option value="24px">Rounded (24px)</option>
                  </select>
                  <p className="text-xs text-gray-500 mt-1">
                    Roundness of buttons and cards
                  </p>
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-2">
                    Spacing Unit
                  </label>
                  <select
                    value={layout.spacing_unit}
                    onChange={(e) => handleLayoutChange('spacing_unit', e.target.value)}
                    className="w-full px-3 sm:px-4 py-2.5 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent text-sm sm:text-base"
                  >
                    <option value="12px">Compact (12px)</option>
                    <option value="16px">Normal (16px)</option>
                    <option value="20px">Comfortable (20px)</option>
                    <option value="24px">Spacious (24px)</option>
                  </select>
                  <p className="text-xs text-gray-500 mt-1">
                    Base spacing between elements
                  </p>
                </div>
              </div>
            </AccordionSection>
          </div>

          {/* Preview Panel - Desktop Sticky, Mobile Bottom */}
          {showPreview && (
            <div className="lg:col-span-1">
              <div className="bg-white rounded-lg border border-gray-200 p-4 sm:p-6 lg:sticky lg:top-6">
                <h2 className="text-base sm:text-lg font-semibold text-gray-900 mb-4">Live Preview</h2>
                
                <PreviewPanel
                  colors={colors}
                  branding={branding}
                  logoUrl={logos.light}
                />
              </div>
            </div>
          )}
        </div>

        {/* Image Preview Modal */}
        <ImagePreviewModal
          isOpen={previewModal.isOpen}
          onClose={closePreviewModal}
          onConfirm={confirmLogoUpload}
          file={previewModal.file}
          previewUrl={previewModal.previewUrl}
          logoType={previewModal.logoType}
        />
      </div>
    </div>
  );
}

// Accordion Section Component
interface AccordionSectionProps {
  title: string;
  isExpanded: boolean;
  onToggle: () => void;
  children: React.ReactNode;
}

function AccordionSection({ title, isExpanded, onToggle, children }: AccordionSectionProps) {
  return (
    <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
      <button
        onClick={onToggle}
        className="w-full flex items-center justify-between px-4 sm:px-6 py-3 sm:py-4 hover:bg-gray-50 transition-colors min-touch-target"
      >
        <h2 className="text-base sm:text-lg font-semibold text-gray-900">{title}</h2>
        {isExpanded ? (
          <ChevronUp className="w-5 h-5 text-gray-500" />
        ) : (
          <ChevronDown className="w-5 h-5 text-gray-500" />
        )}
      </button>
      {isExpanded && (
        <div className="px-4 sm:px-6 py-4 border-t border-gray-200 animate-fadeIn">
          {children}
        </div>
      )}
    </div>
  );
}

// ColorPicker Component
interface ColorPickerProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  description?: string;
}

function ColorPicker({ label, value, onChange, description }: ColorPickerProps) {
  return (
    <div>
      <label className="block text-sm font-medium text-gray-700 mb-2">
        {label}
      </label>
      <div className="flex items-center gap-3">
        <input
          type="color"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="w-12 h-12 sm:w-14 sm:h-14 rounded border border-gray-300 cursor-pointer flex-shrink-0"
        />
        <div className="flex-1 min-w-0">
          <input
            type="text"
            value={value}
            onChange={(e) => onChange(e.target.value)}
            placeholder="#000000"
            pattern="^#[0-9A-Fa-f]{6}$"
            className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent font-mono text-sm"
          />
          {description && (
            <p className="text-xs text-gray-500 mt-1">{description}</p>
          )}
        </div>
      </div>
    </div>
  );
}

// LogoUploadCard Component
interface LogoUploadCardProps {
  title: string;
  logoUrl: string | null;
  uploading: boolean;
  onUpload: (event: React.ChangeEvent<HTMLInputElement>) => void;
  onDelete: () => void;
}

function LogoUploadCard({ title, logoUrl, uploading, onUpload, onDelete }: LogoUploadCardProps) {
  return (
    <div className="border border-gray-200 rounded-lg p-3 sm:p-4">
      <h3 className="text-sm font-medium text-gray-700 mb-3">{title}</h3>
      
      {logoUrl ? (
        <div className="space-y-3">
          <div className="w-full h-24 sm:h-32 bg-gray-50 rounded-lg flex items-center justify-center border border-gray-200">
            <img
              src={logoUrl}
              alt={title}
              className="max-w-full max-h-full object-contain p-2"
              onError={(e) => {
                console.error('Failed to load logo:', logoUrl);
                e.currentTarget.src = 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" width="100" height="100"%3E%3Ctext x="50%25" y="50%25" text-anchor="middle" dy=".3em" fill="%23999"%3EError%3C/text%3E%3C/svg%3E';
              }}
            />
          </div>
          <button
            onClick={onDelete}
            className="w-full flex items-center justify-center gap-2 px-3 py-2 text-sm text-red-600 border border-red-200 rounded-lg hover:bg-red-50 transition-colors min-touch-target"
          >
            <X className="w-4 h-4" />
            Remove
          </button>
        </div>
      ) : (
        <label className="block">
          <input
            type="file"
            accept="image/png,image/jpeg,image/svg+xml,image/x-icon"
            onChange={onUpload}
            className="hidden"
            disabled={uploading}
          />
          <div className="w-full h-24 sm:h-32 bg-gray-50 rounded-lg flex flex-col items-center justify-center border-2 border-dashed border-gray-300 cursor-pointer hover:border-primary-500 hover:bg-primary-50 transition-colors">
            {uploading ? (
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600"></div>
            ) : (
              <>
                <Upload className="w-6 h-6 sm:w-8 sm:h-8 text-gray-400 mb-2" />
                <span className="text-xs sm:text-sm text-gray-500 text-center px-2">Click to upload</span>
                <span className="text-xs text-gray-400 mt-1">PNG, JPG, SVG, ICO</span>
              </>
            )}
          </div>
        </label>
      )}
    </div>
  );
}

// PreviewPanel Component
interface PreviewPanelProps {
  colors: Record<string, string>;
  branding: {
    app_name: string;
    app_tagline: string;
  };
  logoUrl: string | null;
}

function PreviewPanel({ colors, branding, logoUrl }: PreviewPanelProps) {
  return (
    <div className="space-y-4">
      {/* Logo Preview */}
      <div className="border border-gray-200 rounded-lg p-3 sm:p-4 bg-gray-50">
        <p className="text-xs font-medium text-gray-600 mb-2">Logo</p>
        <div className="h-12 sm:h-16 flex items-center justify-center bg-white rounded border border-gray-200">
          {logoUrl ? (
            <img src={logoUrl} alt="Logo" className="max-h-10 sm:max-h-12 max-w-full object-contain" />
          ) : (
            <div 
              className="w-8 h-8 sm:w-10 sm:h-10 rounded-lg flex items-center justify-center"
              style={{ backgroundColor: colors.primary }}
            >
              <span className="text-white font-bold text-sm sm:text-base">
                {branding.app_name?.charAt(0) || 'N'}
              </span>
            </div>
          )}
        </div>
      </div>

      {/* App Name */}
      {branding.app_name && (
        <div className="border border-gray-200 rounded-lg p-3 sm:p-4 bg-gray-50">
          <p className="text-xs font-medium text-gray-600 mb-2">App Name</p>
          <p 
            className="font-semibold text-base sm:text-lg break-words"
            style={{ color: colors.text_primary }}
          >
            {branding.app_name}
          </p>
        </div>
      )}

      {/* Button Preview */}
      <div className="border border-gray-200 rounded-lg p-3 sm:p-4 bg-gray-50">
        <p className="text-xs font-medium text-gray-600 mb-3">Buttons</p>
        <div className="space-y-2">
          <button
            className="w-full px-4 py-2 rounded-lg font-medium transition-opacity hover:opacity-90 text-sm sm:text-base"
            style={{
              backgroundColor: colors.button_primary || colors.primary,
              color: colors.button_text
            }}
          >
            Primary Button
          </button>
          <button
            className="w-full px-4 py-2 rounded-lg font-medium border text-sm sm:text-base"
            style={{
              borderColor: colors.primary,
              color: colors.primary,
              backgroundColor: 'transparent'
            }}
          >
            Secondary Button
          </button>
        </div>
      </div>

      {/* Color Palette */}
      <div className="border border-gray-200 rounded-lg p-3 sm:p-4 bg-gray-50">
        <p className="text-xs font-medium text-gray-600 mb-3">Color Palette</p>
        <div className="grid grid-cols-3 gap-2">
          <ColorSwatch label="Primary" color={colors.primary} />
          <ColorSwatch label="Secondary" color={colors.secondary} />
          <ColorSwatch label="Accent" color={colors.accent} />
        </div>
      </div>

      {/* Text Preview */}
      <div className="border border-gray-200 rounded-lg p-3 sm:p-4" style={{ backgroundColor: colors.background }}>
        <p 
          className="text-sm font-medium mb-2"
          style={{ color: colors.text_primary }}
        >
          Primary Text
        </p>
        <p 
          className="text-xs sm:text-sm"
          style={{ color: colors.text_secondary }}
        >
          Secondary text color for descriptions and less important information.
        </p>
      </div>
    </div>
  );
}

// ColorSwatch Component
interface ColorSwatchProps {
  label: string;
  color: string;
}

function ColorSwatch({ label, color }: ColorSwatchProps) {
  return (
    <div className="text-center">
      <div
        className="w-full h-10 sm:h-12 rounded-lg border border-gray-200 mb-1"
        style={{ backgroundColor: color }}
      ></div>
      <p className="text-xs text-gray-600 truncate">{label}</p>
    </div>
  );
}