/**
 * The only content shown in the signed-in area while the active organisation's
 * membership is unconfirmed. It carries no title, organisation name, status
 * text or data: a static block marks the area as busy, and the label is for
 * assistive technology only. The shell's column rects are unchanged around it.
 */
export function PageLoading() {
  return (
    <div
      className="app-loading"
      role="status"
      aria-busy="true"
      aria-label="Loading"
    />
  )
}
