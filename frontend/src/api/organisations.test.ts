import { describe, expect, it } from 'vitest'
import {
  parseOrganisationCreationResponse,
  parseOrganisationsResponse,
} from './organisations'

describe('parseOrganisationsResponse', () => {
  it('maps the owner marker and creation time', () => {
    expect(
      parseOrganisationsResponse({
        organisations: [
          {
            organisation_id: 'org_1',
            is_owner: true,
            created_at: '2026-01-02T03:04:05Z',
          },
        ],
      }),
    ).toEqual([
      {
        organisationId: 'org_1',
        isOwner: true,
        createdAt: '2026-01-02T03:04:05Z',
      },
    ])
  })

  it('accepts an empty list', () => {
    expect(parseOrganisationsResponse({ organisations: [] })).toEqual([])
  })

  it('rejects a body without a list', () => {
    expect(() => parseOrganisationsResponse({})).toThrow()
    expect(() => parseOrganisationsResponse(null)).toThrow()
  })

  it('rejects a row with no owner marker or invalid time', () => {
    expect(() =>
      parseOrganisationsResponse({
        organisations: [
          {
            organisation_id: 'org_1',
            is_owner: 'yes',
            created_at: '2026-01-02T03:04:05Z',
          },
        ],
      }),
    ).toThrow()
    expect(() =>
      parseOrganisationsResponse({
        organisations: [
          {
            organisation_id: 'org_1',
            is_owner: true,
            created_at: 'not-a-date',
          },
        ],
      }),
    ).toThrow()
  })
})

describe('parseOrganisationCreationResponse', () => {
  it('returns the organisation identifier', () => {
    expect(parseOrganisationCreationResponse({ organisation_id: 'org_1' })).toBe('org_1')
  })

  it('rejects a missing or blank identifier', () => {
    expect(() => parseOrganisationCreationResponse({})).toThrow()
    expect(() => parseOrganisationCreationResponse({ organisation_id: '' })).toThrow()
    expect(() => parseOrganisationCreationResponse({ organisation_id: '   ' })).toThrow()
  })

  it('rejects a body that is not an object', () => {
    expect(() => parseOrganisationCreationResponse(null)).toThrow()
    expect(() => parseOrganisationCreationResponse('org_1')).toThrow()
  })
})
