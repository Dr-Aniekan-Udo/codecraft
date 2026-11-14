import { describe, expect, it } from 'vitest'
import type { MembershipState } from '../api/useMembershipStatus'
import { isMembershipPending, membershipExplanation } from './membership'

describe('isMembershipPending', () => {
  it('treats only idle and checking as pending', () => {
    const expected: Record<MembershipState, boolean> = {
      idle: true,
      checking: true,
      member: false,
      forbidden: false,
      syncing: false,
      unavailable: false,
    }

    for (const [state, pending] of Object.entries(expected)) {
      expect(isMembershipPending(state as MembershipState)).toBe(pending)
    }
  })
})

describe('membershipExplanation', () => {
  it('explains only the final states that have no organisation data', () => {
    const expected: Record<MembershipState, string | null> = {
      idle: null,
      checking: null,
      member: null,
      syncing: 'Organisation syncing. Access has not been confirmed yet.',
      forbidden: 'No access to this organisation.',
      unavailable: 'Access could not be confirmed. Try again.',
    }

    for (const [state, explanation] of Object.entries(expected)) {
      expect(membershipExplanation(state as MembershipState)).toBe(explanation)
    }
  })
})
