import { useBrand } from '../../contexts/BrandContext';
import { useTheme } from '../../contexts/ThemeContext';
import { getFullAssetUrl } from '../../utils/apiBase';
import { cn } from '../../ui';

/**
 * The organization's mark. The brand colour appears here and nowhere else
 * (Design.md). A logo, when set, replaces the text wordmark; the dark logo is
 * used on the dark theme when provided.
 */
export function Wordmark({ size = 'md', className }: { size?: 'md' | 'lg'; className?: string }) {
  const { brand } = useBrand();
  const { resolved } = useTheme();
  const logo = resolved === 'dark' ? brand.logoDarkUrl || brand.logoUrl : brand.logoUrl;

  if (logo) {
    return (
      <img
        src={getFullAssetUrl(logo)}
        alt={brand.appName}
        className={cn('w-auto object-contain', size === 'lg' ? 'h-10' : 'h-7', className)}
      />
    );
  }
  return (
    <span
      className={cn(
        'font-heavy text-brand',
        size === 'lg' ? 'text-heading-lg' : 'text-heading-sm',
        className
      )}
    >
      {brand.appName}
    </span>
  );
}
