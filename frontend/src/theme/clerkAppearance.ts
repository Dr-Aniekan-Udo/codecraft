import type { ResolvedTheme } from '../lib/theme'

const FONT_SANS = 'system-ui, -apple-system, "Segoe UI", sans-serif'
const FONT_MONO = 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace'

/**
 * Clerk uses the same ink palette as the application. Primary actions are
 * inverted ink, never blue: blue belongs to edges and the focus ring. The
 * avatar is sized here because Clerk exposes it as an appearance element in
 * the installed v6 release.
 */
export function clerkAppearanceFor(theme: ResolvedTheme) {
  const dark = theme === 'dark'
  const foreground = dark ? '#FFFFFF' : '#000000'
  const background = dark ? '#000000' : '#FFFFFF'

  return {
    variables: {
      colorPrimary: foreground,
      colorPrimaryForeground: background,
      colorDanger: foreground,
      colorSuccess: foreground,
      colorWarning: foreground,
      colorNeutral: foreground,
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
      borderRadius: '6px',
      spacing: '0.875rem',
    },
    elements: {
      userButtonAvatarBox: {
        width: '24px',
        height: '24px',
        borderRadius: '50%',
        overflow: 'hidden',
      },
      userButtonTrigger: {
        width: '24px',
        height: '24px',
        borderRadius: '50%',
      },
    },
  }
}
