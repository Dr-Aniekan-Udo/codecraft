import { useMembershipStatus } from '../api/useMembershipStatus'
import type { MembershipState } from '../api/useMembershipStatus'

const STATUS_TEXT: Record<MembershipState, string> = {
  idle: 'Waiting for an active team.',
  loading: 'Checking your access…',
  member: 'You have access to this team.',
  forbidden: 'No access to this team.',
  unavailable: 'Team syncing. Access has not been confirmed yet.',
}

export function MembershipStatus({ apiUrl }: { apiUrl: string }) {
  const state = useMembershipStatus(apiUrl)

  return (
    <section className="membership" aria-labelledby="membership-title" data-state={state}>
      <h2 id="membership-title" className="membership__title">
        Membership
      </h2>
      <p className="membership__state" role="status" aria-live="polite">
        {STATUS_TEXT[state]}
      </p>
    </section>
  )
}
