import type { MembershipState } from '../api/useMembershipStatus'

/**
 * True while the active organisation's membership has no answer yet. A member,
 * forbidden or unavailable result is final. Syncing is a membership write that
 * was started deliberately, so it keeps its own message instead of the
 * anonymous loading state.
 */
export function isMembershipPending(
  state: MembershipState,
): state is 'idle' | 'checking' {
  return state === 'idle' || state === 'checking'
}

const EXPLANATIONS: Record<'syncing' | 'forbidden' | 'unavailable', string> = {
  syncing: 'Organisation syncing. Access has not been confirmed yet.',
  forbidden: 'No access to this organisation.',
  unavailable: 'Access could not be confirmed. Try again.',
}

/**
 * The centre column's plain line for a final state that has no organisation
 * data to show. A confirmed member has nothing to explain.
 */
export function membershipExplanation(state: MembershipState): string | null {
  if (state === 'member' || state === 'idle' || state === 'checking') return null
  return EXPLANATIONS[state]
}
