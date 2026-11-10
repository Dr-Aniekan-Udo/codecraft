import { MembershipStatus } from '../components/MembershipStatus'

export function HomePage({ apiUrl }: { apiUrl: string }) {
  return (
    <section className="home" aria-labelledby="page-title">
      <h1 id="page-title" className="home__title">
        CodeCraft
      </h1>
      <MembershipStatus apiUrl={apiUrl} />
    </section>
  )
}
