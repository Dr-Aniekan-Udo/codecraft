import { useAuth, useOrganizationList } from '@clerk/react'
import { useEffect, useRef, useState } from 'react'
import type { KeyboardEvent as ReactKeyboardEvent } from 'react'
import { Link, useNavigate } from 'react-router'
import { subscribeToOrganisationChanges } from '../lib/organisationEvents'

type OrganisationOption = {
  membershipId: string
  id: string
  name: string
}

export function OrganisationSwitcher({
  organisationName,
  showOrganisationNames,
}: {
  organisationName: string | null
  showOrganisationNames: boolean
}) {
  const { orgId: activeOrganisationId } = useAuth()
  const navigate = useNavigate()
  // Clerk's API uses the US spelling 'organization'; the application's domain
  // term is 'organisation'.
  const { isLoaded, setActive, userMemberships } = useOrganizationList({
    userMemberships: { infinite: true, pageSize: 100 },
  })
  const [open, setOpen] = useState(false)
  const [switching, setSwitching] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const triggerRef = useRef<HTMLButtonElement>(null)
  const menuRef = useRef<HTMLDivElement>(null)
  const revalidateMemberships = userMemberships.revalidate

  useEffect(() => {
    return subscribeToOrganisationChanges(() => {
      void revalidateMemberships?.()
    })
  }, [revalidateMemberships])

  const organisations: OrganisationOption[] = (userMemberships.data ?? []).map(
    (membership) => ({
      membershipId: membership.id,
      id: membership.organization.id,
      name: membership.organization.name,
    }),
  )
  const canSwitch =
    isLoaded &&
    setActive !== undefined &&
    !userMemberships.isError &&
    organisations.length > 0

  useEffect(() => {
    if (!open) return
    const menu = menuRef.current
    if (!menu) return
    const activeItem = menu.querySelector<HTMLButtonElement>(
      '[aria-checked="true"]',
    )
    const firstItem = menu.querySelector<HTMLButtonElement>(
      '[role="menuitemradio"]',
    )
    ;(activeItem ?? firstItem)?.focus()
  }, [canSwitch, open])

  useEffect(() => {
    if (!open) return

    function handlePointerDown(event: PointerEvent) {
      if (!containerRef.current?.contains(event.target as Node)) {
        setOpen(false)
      }
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key !== 'Escape') return
      setOpen(false)
      triggerRef.current?.focus()
    }

    document.addEventListener('pointerdown', handlePointerDown)
    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('pointerdown', handlePointerDown)
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [open])

  function toggleMenu(): void {
    if (!canSwitch || switching) return
    setError(null)
    setOpen((current) => !current)
  }

  async function selectOrganisation(organisationId: string): Promise<void> {
    setOpen(false)
    if (organisationId === activeOrganisationId) return
    if (!setActive) return

    setSwitching(true)
    setError(null)
    try {
      await setActive({ organization: organisationId })
      navigate('/')
    } catch {
      setError('Could not switch organisation.')
    } finally {
      setSwitching(false)
    }
  }

  function handleMenuKeyDown(event: ReactKeyboardEvent<HTMLDivElement>): void {
    const items = Array.from(
      menuRef.current?.querySelectorAll<HTMLButtonElement>(
        '[role="menuitemradio"]',
      ) ?? [],
    )
    if (items.length === 0) return

    const current = items.indexOf(document.activeElement as HTMLButtonElement)
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      items[(current + 1) % items.length]?.focus()
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      items[(current - 1 + items.length) % items.length]?.focus()
    } else if (event.key === 'Home') {
      event.preventDefault()
      items[0]?.focus()
    } else if (event.key === 'End') {
      event.preventDefault()
      items[items.length - 1]?.focus()
    }
  }

  return (
    <div className="org-switcher" ref={containerRef}>
      <div className="org-control">
        {organisationName ? (
          <Link
            to="/"
            className="org-control__name"
            title={organisationName}
            onClick={() => setOpen(false)}
          >
            <span className="visually-hidden">Current organisation: </span>
            {organisationName}
          </Link>
        ) : (
          <span className="org-control__name" aria-hidden="true" />
        )}
        <button
          ref={triggerRef}
          type="button"
          className="org-control__chevron"
          aria-label="Switch organisation"
          aria-haspopup="menu"
          aria-expanded={open}
          aria-controls="organisation-switcher-menu"
          aria-busy={switching}
          onClick={toggleMenu}
          disabled={!canSwitch || switching}
        >
          <svg
            viewBox="0 0 16 16"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.4"
            aria-hidden="true"
            focusable="false"
          >
            <path d="m4 6 4 4 4-4" />
          </svg>
        </button>
      </div>

      {open && canSwitch ? (
        <div
          ref={menuRef}
          id="organisation-switcher-menu"
          className="org-menu"
          role="menu"
          aria-label="Switch organisation"
          onKeyDown={handleMenuKeyDown}
        >
          {organisations.map((organisation, index) => {
            const isActive = organisation.id === activeOrganisationId
            const label = showOrganisationNames
              ? organisation.name || organisation.id
              : `Organisation ${index + 1}`

            return (
              <button
                key={organisation.membershipId}
                type="button"
                role="menuitemradio"
                aria-checked={isActive}
                className="org-menu__item"
                onClick={() => void selectOrganisation(organisation.id)}
              >
                <span className="org-menu__check" aria-hidden="true">
                  {isActive ? '✓' : ''}
                </span>
                <span className="org-menu__name">{label}</span>
              </button>
            )
          })}
        </div>
      ) : null}

      {error ? (
        <p className="org-switcher__error" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  )
}
