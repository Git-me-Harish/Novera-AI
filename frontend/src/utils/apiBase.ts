/**
 * Centralised API base URL resolver.
 *
 * Rules (in priority order):
 *  1. VITE_API_URL env var — set this in Render's environment variables to
 *     your deployed backend URL (e.g. https://novera-backend.onrender.com).
 *  2. Empty string  — when the frontend is served BY the backend (single-
 *     origin deployment on Render) relative paths work perfectly, so we
 *     default to '' rather than localhost.
 *
 * The old pattern `|| 'http://localhost:8000'` was scattered across 5 files
 * and would silently produce broken image/asset URLs in production whenever
 * VITE_API_URL was not set at build time.
 *
 * Usage:
 *   import { apiBase, getFullAssetUrl } from '@/utils/apiBase';
 *
 *   // Raw base (for constructing API paths programmatically)
 *   const url = `${apiBase}/api/v1/something`;
 *
 *   // Asset URLs (branding images, uploads, etc.)
 *   const logoSrc = getFullAssetUrl(customization.branding.logo_url);
 */

/**
 * The API base URL with no trailing slash.
 * Empty string = same-origin (correct for single-container Render deploys).
 */
export const apiBase: string = (import.meta.env.VITE_API_URL ?? '').replace(/\/$/, '');

/**
 * Resolve a server-relative path (e.g. "/uploads/branding/logo.png") to a
 * fully-qualified URL.  Absolute URLs (http/https) are returned unchanged.
 *
 * @param path  - Relative or absolute path returned by the backend.
 * @returns     - Fully qualified URL safe to use in <img src=...>.
 */
export function getFullAssetUrl(path: string | null | undefined): string {
  if (!path) return '';
  if (path.startsWith('http://') || path.startsWith('https://')) return path;
  return `${apiBase}${path.startsWith('/') ? '' : '/'}${path}`;
}
