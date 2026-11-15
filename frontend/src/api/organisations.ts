export type OrganisationSummary = {
  organisationId: string
  isOwner: boolean
  createdAt: string
}

export type OrganisationMemberRole = 'org:admin' | 'org:member'

export class OrganisationRequestError extends Error {
  readonly status: number
  readonly detail: string | null

  constructor(status: number, message: string, detail: string | null = null) {
    super(message)
    this.name = 'OrganisationRequestError'
    this.status = status
    this.detail = detail
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function nonEmptyString(value: unknown): value is string {
  return typeof value === 'string' && value.trim().length > 0
}

async function requestError(
  response: Response,
  fallback: string,
): Promise<OrganisationRequestError> {
  let detail: string | null = null
  try {
    const body: unknown = await response.json()
    if (isRecord(body) && typeof body['detail'] === 'string') {
      detail = body['detail']
    }
  } catch {
    // A response without a JSON body still carries its status.
  }
  return new OrganisationRequestError(response.status, detail ?? fallback, detail)
}

export function parseOrganisationsResponse(body: unknown): OrganisationSummary[] {
  if (!isRecord(body) || !Array.isArray(body['organisations'])) {
    throw new Error('The organisations response has no list.')
  }

  return body['organisations'].map((value, index) => {
    if (!isRecord(value)) {
      throw new Error(`Organisation at index ${index} is not an object.`)
    }
    const organisationId = value['organisation_id']
    const isOwner = value['is_owner']
    const createdAt = value['created_at']
    if (!nonEmptyString(organisationId)) {
      throw new Error(`Organisation at index ${index} has no identifier.`)
    }
    if (typeof isOwner !== 'boolean') {
      throw new Error(`Organisation at index ${index} has no owner marker.`)
    }
    if (!nonEmptyString(createdAt) || Number.isNaN(Date.parse(createdAt))) {
      throw new Error(`Organisation at index ${index} has no valid creation time.`)
    }
    return { organisationId, isOwner, createdAt }
  })
}

export function parseOrganisationCreationResponse(body: unknown): string {
  if (!isRecord(body)) {
    throw new Error('The organisation creation response is not an object.')
  }
  const organisationId = body['organisation_id']
  if (!nonEmptyString(organisationId)) {
    throw new Error('The organisation creation response has no identifier.')
  }
  return organisationId
}

export async function fetchOrganisations(
  apiUrl: string,
  token: string,
  signal?: AbortSignal,
): Promise<OrganisationSummary[]> {
  const response = await fetch(`${apiUrl}/v1/organisations`, {
    method: 'GET',
    headers: {
      Accept: 'application/json',
      Authorization: `Bearer ${token}`,
    },
    signal,
  })
  if (!response.ok) {
    throw await requestError(response, 'The organisations list could not be loaded.')
  }
  return parseOrganisationsResponse(await response.json())
}

export async function createOrganisation(
  apiUrl: string,
  token: string,
  options: { name: string; idempotencyKey: string },
): Promise<string> {
  const response = await fetch(`${apiUrl}/v1/organisations`, {
    method: 'POST',
    headers: {
      Accept: 'application/json',
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      name: options.name,
      idempotency_key: options.idempotencyKey,
    }),
  })
  if (!response.ok) {
    throw await requestError(response, 'The organisation could not be created.')
  }
  return parseOrganisationCreationResponse(await response.json())
}

export async function createPersonalOrganisation(
  apiUrl: string,
  token: string,
  idempotencyKey: string,
): Promise<string> {
  const response = await fetch(`${apiUrl}/v1/organisations/personal`, {
    method: 'POST',
    headers: {
      Accept: 'application/json',
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ idempotency_key: idempotencyKey }),
  })
  if (!response.ok) {
    throw await requestError(response, 'The personal organisation could not be created.')
  }
  return parseOrganisationCreationResponse(await response.json())
}

export async function removeOrganisationMember(
  apiUrl: string,
  token: string,
  organisationId: string,
  memberUserId: string,
): Promise<void> {
  const response = await fetch(
    `${apiUrl}/v1/organisations/${encodeURIComponent(organisationId)}/members/${encodeURIComponent(memberUserId)}`,
    {
      method: 'DELETE',
      headers: {
        Accept: 'application/json',
        Authorization: `Bearer ${token}`,
      },
    },
  )
  if (!response.ok) {
    throw await requestError(response, 'The member could not be removed.')
  }
}

export async function leaveOrganisation(
  apiUrl: string,
  token: string,
  organisationId: string,
  memberUserId: string,
): Promise<void> {
  return removeOrganisationMember(apiUrl, token, organisationId, memberUserId)
}

export async function updateOrganisationMemberRole(
  apiUrl: string,
  token: string,
  organisationId: string,
  memberUserId: string,
  role: OrganisationMemberRole,
): Promise<void> {
  const response = await fetch(
    `${apiUrl}/v1/organisations/${encodeURIComponent(organisationId)}/members/${encodeURIComponent(memberUserId)}`,
    {
      method: 'PATCH',
      headers: {
        Accept: 'application/json',
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ role }),
    },
  )
  if (!response.ok) {
    throw await requestError(response, 'The member role could not be changed.')
  }
}
