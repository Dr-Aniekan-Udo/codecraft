import type { ThemePreference } from '../lib/theme'
import { useTheme } from '../theme/context'

const PREFERENCE_LABEL: Record<ThemePreference, string> = {
  system: 'System',
  light: 'Light',
  dark: 'Dark',
}

const NEXT_PREFERENCE: Record<ThemePreference, ThemePreference> = {
  system: 'light',
  light: 'dark',
  dark: 'system',
}

function ThemeGlyph({ preference }: { preference: ThemePreference }) {
  if (preference === 'system') {
    return (
      <svg
        viewBox="0 0 16 16"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.2"
        aria-hidden="true"
        focusable="false"
      >
        <circle cx="8" cy="8" r="5.5" />
        <path
          d="M8 2.5a5.5 5.5 0 0 1 0 11Z"
          fill="currentColor"
          stroke="none"
        />
      </svg>
    )
  }

  if (preference === 'light') {
    return (
      <svg
        viewBox="0 0 16 16"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.2"
        aria-hidden="true"
        focusable="false"
      >
        <circle cx="8" cy="8" r="3" />
        <path d="M8 1.5v1.4M8 13.1v1.4M1.5 8h1.4M13.1 8h1.4M3.4 3.4l1 1M11.6 11.6l1 1M12.6 3.4l-1 1M4.4 11.6l-1 1" />
      </svg>
    )
  }

  return (
    <svg
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.2"
      aria-hidden="true"
      focusable="false"
    >
      <path d="M10.8 2.6a5.4 5.4 0 1 0 3 8.8 4.3 4.3 0 0 1-3-8.8Z" />
    </svg>
  )
}

export function ThemeControl() {
  const { preference, resolved, setPreference } = useTheme()
  const preferenceLabel = PREFERENCE_LABEL[preference]
  const accessibleName =
    preference === 'system'
      ? `Theme: System, ${resolved}. Activate to change the theme.`
      : `Theme: ${preferenceLabel}. Activate to change the theme.`

  return (
    <span className="theme-control">
      <button
        type="button"
        className="icon-button"
        aria-label={accessibleName}
        onClick={() => setPreference(NEXT_PREFERENCE[preference])}
      >
        <ThemeGlyph preference={preference} />
      </button>
      <span className="theme-tooltip" aria-hidden="true">
        Theme: {preferenceLabel}
      </span>
    </span>
  )
}
