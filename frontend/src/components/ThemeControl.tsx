import { useTheme } from '../theme/context'
import type { ThemePreference } from '../lib/theme'

const OPTIONS: ReadonlyArray<{ value: ThemePreference; label: string }> = [
  { value: 'system', label: 'System' },
  { value: 'light', label: 'Light' },
  { value: 'dark', label: 'Dark' },
]

export function ThemeControl() {
  const { preference, setPreference } = useTheme()

  return (
    <fieldset className="theme-control">
      <legend className="visually-hidden">Theme</legend>
      {OPTIONS.map((option) => (
        <label className="theme-control__option" key={option.value}>
          <input
            type="radio"
            name="theme"
            value={option.value}
            checked={preference === option.value}
            onChange={() => setPreference(option.value)}
          />
          <span>{option.label}</span>
        </label>
      ))}
    </fieldset>
  )
}
