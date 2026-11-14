import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { NOT_FOUND_MESSAGE, NotFoundMessage } from './NotFoundMessage'

describe('NotFoundMessage', () => {
  it('renders the same markup and message for the project and analysis cases', () => {
    const projectMarkup = renderToStaticMarkup(
      <NotFoundMessage message={NOT_FOUND_MESSAGE} />,
    )
    const analysisMarkup = renderToStaticMarkup(
      <NotFoundMessage message={NOT_FOUND_MESSAGE} />,
    )
    expect(projectMarkup).toBe(analysisMarkup)
    expect(projectMarkup).toBe(
      `<p class="plain-line" role="status">${NOT_FOUND_MESSAGE}</p>`,
    )
  })
})
