import { describe, expect, it } from 'vitest'
import { resolveTeamName, teamNameForAccount, teamNameForEmail } from './identity'

describe('teamNameForEmail', () => {
  it('uses the local part before the @', () => {
    expect(teamNameForEmail('ada@example.com')).toBe("ada's team")
  })

  it('keeps dots and plus signs exactly', () => {
    expect(teamNameForEmail('first.last+test@example.com')).toBe("first.last+test's team")
  })

  it('uses My team when there is no email', () => {
    expect(teamNameForEmail(null)).toBe('My team')
    expect(teamNameForEmail(undefined)).toBe('My team')
    expect(teamNameForEmail('')).toBe('My team')
  })
})

describe('teamNameForAccount', () => {
  it('uses the email, not the first name', () => {
    const account = {
      primaryEmailAddress: { emailAddress: 'ada@example.com' },
      firstName: 'Ada',
    }

    expect(teamNameForAccount(account)).toBe("ada's team")
  })

  it('uses My team when the account has no email', () => {
    const account = {
      primaryEmailAddress: null,
      firstName: 'Ada',
    }

    expect(teamNameForAccount(account)).toBe('My team')
  })
})

describe('resolveTeamName', () => {
  it('prefers the org_name claim', () => {
    expect(resolveTeamName({ org_name: 'Acme', o: { id: 'org_123' } }, 'org_456')).toBe('Acme')
  })

  it('falls back to the standard o.id claim', () => {
    expect(resolveTeamName({ o: { id: 'org_123' } }, 'org_456')).toBe('org_123')
  })

  it('ignores the legacy org_id claim', () => {
    expect(resolveTeamName({ org_id: 'org_old', o: { id: 'org_123' } }, 'org_456')).toBe(
      'org_123',
    )
  })

  it('falls back to the active organization id', () => {
    expect(resolveTeamName({}, 'org_456')).toBe('org_456')
    expect(resolveTeamName(null, 'org_456')).toBe('org_456')
  })

  it('ignores blank and non-string claims', () => {
    expect(resolveTeamName({ org_name: '  ', o: { id: 42 } }, 'org_456')).toBe('org_456')
    expect(resolveTeamName({ o: { id: '   ' } }, 'org_456')).toBe('org_456')
  })

  it('returns a no-team state when no identifier is known', () => {
    expect(resolveTeamName(null, null)).toBe('No team')
  })
})
