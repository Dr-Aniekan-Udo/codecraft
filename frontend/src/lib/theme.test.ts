import { describe, expect, it } from 'vitest'
import { parseThemePreference, resolveTheme } from './theme'

describe('parseThemePreference', () => {
  it('accepts the three stored values', () => {
    expect(parseThemePreference('system')).toBe('system')
    expect(parseThemePreference('light')).toBe('light')
    expect(parseThemePreference('dark')).toBe('dark')
  })

  it('treats missing and unknown values as system', () => {
    expect(parseThemePreference(null)).toBe('system')
    expect(parseThemePreference(undefined)).toBe('system')
    expect(parseThemePreference('sepia')).toBe('system')
  })
})

describe('resolveTheme', () => {
  it('follows the system preference', () => {
    expect(resolveTheme('system', true)).toBe('dark')
    expect(resolveTheme('system', false)).toBe('light')
  })

  it('keeps a forced choice regardless of the system', () => {
    expect(resolveTheme('light', true)).toBe('light')
    expect(resolveTheme('dark', false)).toBe('dark')
  })
})
