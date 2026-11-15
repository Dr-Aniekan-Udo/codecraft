export const NOT_FOUND_MESSAGE = 'This page could not be found.'

/**
 * The project and analysis pages both have exactly one not-found answer. The
 * markup depends only on the message, so neither page can drift from the other.
 */
export function NotFoundMessage({
  message = NOT_FOUND_MESSAGE,
}: {
  message?: string
}) {
  return (
    <p className="plain-line" role="status">
      {message}
    </p>
  )
}
