import { describe, expect, it } from 'vitest'
import { organisationNameFromToken, resolveOrganisationName } from './identity'

function tokenWithPayload(payload: unknown): string {
  const encoded = btoa(JSON.stringify(payload))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '')
  return `header.${encoded}.signature`
}

describe('resolveOrganisationName', () => {
  it('uses the org_name claim', () => {
    expect(resolveOrganisationName({ org_name: 'Acme', o: { id: 'org_123' } })).toBe('Acme')
  })

  it('returns null rather than an identifier or placeholder', () => {
    expect(resolveOrganisationName({ o: { id: 'org_123' } })).toBeNull()
    expect(resolveOrganisationName({ org_id: 'org_old' })).toBeNull()
    expect(resolveOrganisationName({})).toBeNull()
    expect(resolveOrganisationName(null)).toBeNull()
  })

  it('ignores blank and non-string claims', () => {
    expect(resolveOrganisationName({ org_name: '  ' })).toBeNull()
    expect(resolveOrganisationName({ org_name: 42 })).toBeNull()
  })
})

describe('organisationNameFromToken', () => {
  it('reads the org_name claim', () => {
    expect(organisationNameFromToken(tokenWithPayload({ org_name: 'Acme' }))).toBe('Acme')
  })

  it('returns null when the claim is absent or blank', () => {
    expect(organisationNameFromToken(tokenWithPayload({ o: { id: 'org_123' } }))).toBeNull()
    expect(organisationNameFromToken(tokenWithPayload({ org_name: '  ' }))).toBeNull()
  })

  it('returns null for a malformed token', () => {
    expect(organisationNameFromToken('not-a-token')).toBeNull()
    expect(organisationNameFromToken('header.%%%.signature')).toBeNull()
  })
})
