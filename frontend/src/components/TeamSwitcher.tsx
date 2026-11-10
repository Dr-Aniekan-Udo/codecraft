import { useAuth, useOrganizationList } from '@clerk/react'
import { useState } from 'react'
import type { ChangeEvent } from 'react'

export function TeamSwitcher() {
  const { orgId } = useAuth()
  const { isLoaded, setActive, userMemberships } = useOrganizationList({
    userMemberships: { infinite: true, pageSize: 100 },
  })
  const [switching, setSwitching] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (!isLoaded || userMemberships.isLoading || userMemberships.isError) return null
  if (!orgId) return null

  const activateOrganization = setActive
  const memberships = userMemberships.data ?? []
  if (memberships.length === 0) return null

  async function handleChange(event: ChangeEvent<HTMLSelectElement>) {
    const nextOrganizationId = event.currentTarget.value
    if (!nextOrganizationId || nextOrganizationId === orgId) return

    setSwitching(true)
    setError(null)
    try {
      await activateOrganization({ organization: nextOrganizationId })
    } catch {
      setError('Could not switch team.')
    } finally {
      setSwitching(false)
    }
  }

  return (
    <div className="team-switcher">
      <label className="visually-hidden" htmlFor="team-switcher">
        Switch team
      </label>
      <select
        id="team-switcher"
        className="select"
        value={orgId ?? ''}
        onChange={(event) => {
          void handleChange(event)
        }}
        disabled={switching}
        aria-busy={switching}
      >
        {memberships.map((membership) => (
          <option value={membership.organization.id} key={membership.id}>
            {membership.organization.name || membership.organization.id}
          </option>
        ))}
      </select>
      {error ? (
        <span className="inline-message" role="alert">
          {error}
        </span>
      ) : null}
    </div>
  )
}
