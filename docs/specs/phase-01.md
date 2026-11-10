# Phase 1 — Identity and teams

**Goal.** Someone signs in, belongs to a team, and every request they make reaches the database as that person, so the database decides what they can see.

Sign-in itself is already set up. This phase is about what has to be true around it.

## Build

- **Teams at first sign-in.** Signing in with no team creates one through the identity provider's client, named by the naming rule, and makes it active. The name is the same whichever sign-in method was used.
- **The naming rule.** The team's name is the part of the person's email before the @, followed by "'s team". For `ada@example.com` the name is "ada's team". If the account has no email, the name is "My team". First and last names are never used. The name is set once, at creation.
- **Invitations.** An admin of a team can invite another person by email. A member cannot invite anyone, and the invite action is not shown to them. Accepting an invitation brings the person to this app's sign-in page, then into that team.
- **Switching.** A person in more than one team can switch which one is active. The whole application shows the new team after the switch.
- **The team name in the header.** The header shows the name carried by the token's display claim, `org_name`, on the first paint. If that claim is absent, the header shows the team's identifier, never a guessed name.
- **Membership.** The identity provider's team events arrive at an endpoint in the API. The endpoint verifies each event's signature before reading it, then writes the membership change. The membership table holds one row per person per team, with row-level security enabled and one policy: a person can read only their own rows.
- **Token check.** The API checks every request's token for signature, issuer and expiry. A missing, expired or altered token is refused with 401.
- **Team check.** The API reads the person's active team from the token's standard organization object, `o.id`. It then checks that the person has a membership row for that team. If the token has no active team, or the person is not a member of it, the API refuses with 403.
- **Database access.** Each request's database work runs as the restricted API role. Inside that transaction, the connection switches to the authenticated role and sets the verified person's identity as the claims that policies read.
- **"Team syncing".** When the membership row has not arrived yet, the page shows a short message saying the team is syncing. It never shows a blank page.
- **Application shell.** The signed-in area renders inside one shell that later phases fill in.
- **Theme control.** Three states: follow the system, force light, force dark. The choice is written to the root element, survives a reload, and the colour tokens respond to it.

## Constraints

- **The token says who. The database says what.** Membership is read from the membership table through the policy on every query. A token that claims a team grants nothing by itself.
- **The team comes from the standard claim.** The active team is read from `o.id`, which the identity provider sends by default. An earlier build read a custom field the token never carried, so every request was refused. Only the display name uses a custom claim.
- **Removal takes effect on the next request.** The policy reads current membership, not the token, so a removed person is refused straight away. Waiting for the token to expire would leave a removed person able to read until it did.
- **Removal leaves no access behind.** Removal from a team takes effect on the person's next request, and that team's data is refused from then on. A person left with no team is given a new team, named by the naming rule, as at a first sign-in. The removed person never regains the old team's data.
- **Membership arrives after the team does.** The team exists before its membership row is written, so a brief 403 right after creation is expected. The page retries once, then shows "Team syncing". A person is never shown a blank page and never shown another team's data.
- **The webhook verifies before it reads.** An event with an invalid signature is refused and writes nothing. Otherwise anyone who finds the address could add people to teams.
- **Pooled database connections can go stale.** The database closes idle connections from its side. A write that reuses one fails at its first statement. So the pool checks each connection before use, keeps idle connections short-lived, and the membership write retries once on a closed connection. Without this, a sign-up can fail once and never recover, leaving a person locked out.
- **Prepared statements are off.** The transaction pooler does not support them, so enabling them causes failures that appear only under load.
- **The membership sync writes through its own narrow role.** That role can change the membership table and nothing else. If it could reach other tables, a bug in the webhook could alter data it has no reason to touch.
- **The API holds no elevated database credential.** Only the restricted API role is loaded. A credential that bypasses row-level security means the policies are silently ignored while everything appears to work.
- **One connection factory.** Every database connection in the API comes from it, because it is the only place that sets the claims. Code that opens a connection another way returns wrong rows without any error.
- **Teams are created only once per sign-in.** Two tabs racing at first sign-in must not create two teams for one person.
- **Invitations are restricted by the identity provider, not only hidden.** The admin-only rule is enforced where invitations are sent, so a member who somehow reaches the action is still refused.
- **One session mechanism.** Sessions belong to the identity provider. Any second mechanism left by a template is removed, because two systems owning one cookie causes sign-outs that look random.
- **The database client carries the token.** A client built without it looks fine until the first policy exists, and then every query returns nothing.
- **The frontend is a single-page application.** The protected-page redirect is for convenience. The real protection is the API and the database, so bypassing the redirect still returns nothing.
- **Configuration fails loudly.** If a required value is missing at startup, the application refuses to start and names the value. A blank value that causes a confusing error later is worse than a crash on start.
- **Only membership is created.** No table other than membership is created in this phase.

## Acceptance check

1. Sign up with a brand-new email account. The team is named "{the part of the email before @}'s team", and the identity provider's create-team screen never appears.
2. Sign up with GitHub or Google. The team is named by the same rule, using the email that provider supplies.
3. An admin invites a second account. It accepts the invitation, arrives at sign-in, and lands in the same team, under the same name.
4. Signed in as a member, the invite action is not visible anywhere in the application.
5. The header shows the team's name on the first paint, with no flicker to another name.
6. Remove the second account from the team. Its next request for that team is refused, without waiting for the token to expire. If it has no other team, it is given a new team with the naming rule, and the old team's data is never shown.
7. Switch to a second team and back. The header and the membership status both change, and no page shows the previous team's data.
8. Switch the theme through all three states and reload each time. The choice survives. Forcing light while the system is dark shows light.
9. Visit a protected page while signed out. Sign-in appears before any of the page's content, and the network tab shows no protected page data.
10. In the database dashboard, the membership table shows row-level security as enabled, with a single policy.

## Not in this phase

Renaming a team from inside the application. Until then, an admin renames it in the identity provider's dashboard. Any table other than membership. Roles beyond owner, admin and member. Custom styling of the sign-in screen beyond matching the rest of the application.
