const ORGANISATIONS_CHANGED_EVENT = 'codecraft:organisations-changed'

export function notifyOrganisationsChanged(): void {
  if (typeof window === 'undefined') return
  window.dispatchEvent(new Event(ORGANISATIONS_CHANGED_EVENT))
}

export function subscribeToOrganisationChanges(handler: () => void): () => void {
  if (typeof window === 'undefined') return () => {}
  window.addEventListener(ORGANISATIONS_CHANGED_EVENT, handler)
  return () => window.removeEventListener(ORGANISATIONS_CHANGED_EVENT, handler)
}
