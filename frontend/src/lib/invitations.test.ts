import { describe, expect, it } from 'vitest'
import { inviterName, pendingInvitationsForUser } from './invitations'
import type { ClerkInvitationRow, InvitationUser } from './invitations'

function invitation(overrides: Partial<ClerkInvitationRow> = {}): ClerkInvitationRow {
  return {
    id: 'inv_1',
    emailAddress: 'ada@example.com',
    publicOrganizationData: { id: 'org_1', name: 'Acme' },
    publicMetadata: { inviter_name: 'Grace Hopper' },
    status: 'pending',
    accept: async () => undefined,
    ...overrides,
  }
}

function user(overrides: Partial<InvitationUser> = {}): InvitationUser {
  return {
    unsafeMetadata: {},
    emailAddresses: [
      {
        emailAddress: 'ada@example.com',
        verification: { status: 'verified' },
      },
    ],
    ...overrides,
  }
}

describe('pendingInvitationsForUser', () => {
  it('maps publicOrganizationData to the local organisation field', () => {
    const [result] = pendingInvitationsForUser([invitation()], user())

    expect(result.organisation).toEqual({ id: 'org_1', name: 'Acme' })
  })

  it('keeps only invitations sent to a verified email address', () => {
    const result = pendingInvitationsForUser(
      [
        invitation(),
        invitation({
          id: 'inv_2',
          emailAddress: 'bob@example.com',
          publicOrganizationData: { id: 'org_2', name: 'Beta' },
        }),
      ],
      user(),
    )

    expect(result.map((item) => item.id)).toEqual(['inv_1'])
  })

  it('keeps only pending invitations', () => {
    const result = pendingInvitationsForUser(
      [
        invitation(),
        invitation({ id: 'inv_2', status: 'accepted' }),
        invitation({ id: 'inv_3', status: 'revoked' }),
      ],
      user(),
    )

    expect(result.map((item) => item.id)).toEqual(['inv_1'])
  })

  it('excludes declined invitation identifiers from user metadata', () => {
    const result = pendingInvitationsForUser(
      [invitation(), invitation({ id: 'inv_2' })],
      user({
        unsafeMetadata: {
          declinedOrganisationInvitationIds: { inv_1: true },
        },
      }),
    )

    expect(result.map((item) => item.id)).toEqual(['inv_2'])
  })
})

describe('inviterName', () => {
  it('prefers the inviter name, then email, then a generic label', () => {
    const [named] = pendingInvitationsForUser([invitation()], user())
    const [emailed] = pendingInvitationsForUser(
      [invitation({ id: 'inv_2', publicMetadata: { inviter_email: 'grace@example.com' } })],
      user(),
    )
    const [anonymous] = pendingInvitationsForUser(
      [invitation({ id: 'inv_3', publicMetadata: {} })],
      user(),
    )
    const [genericWithEmail] = pendingInvitationsForUser(
      [
        invitation({
          id: 'inv_4',
          publicMetadata: {
            inviter_name: 'An organisation admin',
            inviter_email: 'grace@example.com',
          },
        }),
      ],
      user(),
    )

    expect(inviterName(named)).toBe('Grace Hopper')
    expect(inviterName(emailed)).toBe('grace@example.com')
    expect(inviterName(anonymous)).toBe('An organisation admin')
    expect(inviterName(genericWithEmail)).toBe('grace@example.com')
  })
})
