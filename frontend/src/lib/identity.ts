function nonEmptyString(value: unknown): string | null {
  return typeof value === 'string' && value.trim().length > 0 ? value.trim() : null
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

/**
 * Reads the display claim from a token that was just issued by the identity
 * provider. The signature is deliberately not checked; this is display only.
 */
export function organisationNameFromToken(token: string): string | null {
  try {
    const payload = token.split('.')[1]
    if (!payload) return null
    const base64 = payload.replace(/-/g, '+').replace(/_/g, '/')
    const padded = base64.padEnd(Math.ceil(base64.length / 4) * 4, '=')
    const binary = atob(padded)
    const bytes = Uint8Array.from(binary, (character) => character.charCodeAt(0))
    const claims: unknown = JSON.parse(new TextDecoder().decode(bytes))
    if (!isRecord(claims)) return null
    return nonEmptyString(claims['org_name'])
  } catch {
    return null
  }
}

/**
 * The header shows only a real display name, never an identifier or a
 * placeholder. An absent claim means the slot stays empty until the name is
 * available from the freshly loaded organisation.
 */
export function resolveOrganisationName(
  claims: Record<string, unknown> | null | undefined,
): string | null {
  return nonEmptyString(claims?.['org_name'])
}
