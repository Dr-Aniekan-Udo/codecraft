const MONTHS = [
  'Jan',
  'Feb',
  'Mar',
  'Apr',
  'May',
  'Jun',
  'Jul',
  'Aug',
  'Sep',
  'Oct',
  'Nov',
  'Dec',
] as const

/**
 * Timestamps arrive as ISO strings. The workspace shows them in UTC so two
 * people looking at the same analysis read the same time, and the zone is
 * labelled instead of implied.
 */
export function formatUtc(iso: string): string {
  const date = new Date(iso)
  const day = String(date.getUTCDate()).padStart(2, '0')
  const month = MONTHS[date.getUTCMonth()]
  const year = date.getUTCFullYear()
  const hours = String(date.getUTCHours()).padStart(2, '0')
  const minutes = String(date.getUTCMinutes()).padStart(2, '0')
  return `${day} ${month} ${year}, ${hours}:${minutes} UTC`
}
