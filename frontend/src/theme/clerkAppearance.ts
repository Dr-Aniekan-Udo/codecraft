import type { ResolvedTheme } from '../lib/theme'

const FONT_SANS = 'system-ui, -apple-system, "Segoe UI", sans-serif'
const FONT_MONO = 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace'

/**
 * Clerk's variables are derived from the same Okabe-Ito palette as the app.
 * In dark mode primary becomes white because canonical blue is not readable as
 * text on black; blue remains the focus ring and the app's accent.
 */
export function clerkAppearanceFor(theme: ResolvedTheme) {
  const dark = theme === 'dark'
  const foreground = dark ? '#FFFFFF' : '#000000'
  const background = dark ? '#000000' : '#FFFFFF'

  return {
    variables: {
      colorPrimary: dark ? '#FFFFFF' : '#0072B2',
      colorPrimaryForeground: dark ? '#000000' : '#FFFFFF',
      colorDanger: dark ? '#D55E00' : '#000000',
      colorSuccess: dark ? '#FFFFFF' : '#0072B2',
      colorWarning: dark ? '#D55E00' : '#000000',
      colorNeutral: dark ? '#FFFFFF' : '#000000',
      colorForeground: foreground,
      colorMuted: dark ? 'rgba(255, 255, 255, 0.08)' : 'rgba(0, 0, 0, 0.05)',
      colorMutedForeground: dark ? 'rgba(255, 255, 255, 0.74)' : 'rgba(0, 0, 0, 0.72)',
      colorBackground: background,
      colorInput: background,
      colorInputForeground: foreground,
      colorShimmer: dark ? 'rgba(255, 255, 255, 0.12)' : 'rgba(0, 0, 0, 0.08)',
      colorRing: '#0072B2',
      colorShadow: dark ? 'rgba(255, 255, 255, 0.14)' : 'rgba(0, 0, 0, 0.16)',
      colorBorder: dark ? 'rgba(255, 255, 255, 0.55)' : 'rgba(0, 0, 0, 0.55)',
      colorModalBackdrop: 'rgba(0, 0, 0, 0.7)',
      fontFamily: FONT_SANS,
      fontFamilyButtons: FONT_SANS,
      fontFamilyMono: FONT_MONO,
      fontSize: '0.8125rem',
      borderRadius: '3px',
      spacing: '0.875rem',
    },
  }
}
