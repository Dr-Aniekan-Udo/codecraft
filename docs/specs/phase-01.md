# Phase 1 — Identity and organisations

**Goal.** Every person has an organisation of their own from their first sign-in. They can be invited into other organisations, accept or decline those invitations, and switch between their organisations. The database decides what they can see in every organisation.

Sign-in itself is already set up. This phase is about what has to be true around it.

## Build

- **A personal organisation at first sign-in.** A signed-in person who owns no organisation gets one, named by the naming rule, and it becomes active. This applies to every sign-in method, and to accounts that existed before this rule.
- **The naming rule.** A personal organisation's name is "My organisation". The rule is applied when the organisation is created and is never reapplied.
- **Creating an organisation.** A signed-in person can create an organisation with a name they enter. The name is required. The person who creates it becomes its owner and an admin. The request is made to the backend and carries an idempotency key chosen by the browser for that attempt.
- **Inviting.** An admin of an organisation, including its owner, can invite a person by email. The invitation is bound to that email address. An admin can revoke a pending invitation.
- **Pending invitations.** A signed-in person sees the invitations sent to their own verified email address. Each one shows the organisation's name and who sent it, with accept and decline. Nothing has to be typed to find an invitation.
- **Pending invitations on the root page.** The root page lists the pending invitations as plain rows above the analyses section, so a new arrival sees them without opening the invitations page. The rows use the same accept and decline actions as the invitations page.
- **The invitations page.** Invitation emails link to a page in this application. The page lists the pending invitations for the signed-in account. If the account has none, the page says so and tells the person to sign in with the address the invitation was sent to. If the person is not signed in, the page sends them to sign-in and returns them to the same page.
- **Accepting and declining.** Accepting adds the organisation to the person's organisations. It does not make the organisation active; the person switches to it when they choose. Declining hides that invitation for that person. Neither changes the organisation. After either action, the pending list and the switcher reload at once, on whichever page the action was taken.
- **Invitations control.** The header has an Invitations icon, with a count badge when invitations are pending. It opens the invitations page from any page. The badge is ink with a white count, never a hue. Invite is a dialog, as before. Only Invitations is a route. The icon's accessible name states the number pending, or that none are pending, so the control works without a mouse and without relying on a tooltip.
- **One three-column shell.** The signed-in area uses one three-column shell, built once. The left column is a context rail: the selected analysis, the total count, and the words "switch in the centre list". Later phases add coverage and exploration to the rail. The centre column holds the active section. The right column is a detail pane showing the details of the current item. The three columns take 3, 8 and 4 parts of the content width: rail 3, centre 8, pane 4. No column has a fixed pixel width. Later phases fill these columns and do not move them. The rail's position and width do not change.
- **Organisation name in the header.** The header reads, from the left: the brand, then the organisation control. The organisation's name opens the root of the application. The chevron opens the switcher.
- **Switching.** Choosing another organisation in the switcher makes it active and opens that organisation's root, from any page, including the invitations page. The application obtains a fresh token for that organisation and loads its data.
- **Renaming an organisation.** An admin can rename the organisation. After a rename, the header shows the new name straight away.
- **Deleting an organisation.** Only the organisation's owner can delete it. Deletion is offered only when the person owns another organisation that remains.
- **Leaving an organisation.** An owner cannot leave an organisation they own. Ownership transfer is not part of this phase, so the owner's only way out of their own organisation is deletion, which is refused while they own no other organisation.
- **Roles.** The application uses the identity provider's two default roles, admin and member. The owner is the person who created the organisation and holds the admin role. Any number of members can be admins. The owner can promote a member to admin and demote an admin back to member. Admins can remove members, except the owner. Admins cannot promote, demote or delete.
- **Role and member changes go through the backend.** Promoting, demoting and removing members are requests to the backend. The backend checks the acting person's role and the target's role, and only then asks the identity provider to make the change. The application does not call the identity provider's member-management functions directly.
- **Unchanged from the earlier build:** the membership webhook, the token check, the organisation check, the theme control's three states and persistence, the header's control set, the sign-in methods, and the protected-page redirect. The signed-in area below the header gains the three-column shell.

## Constraints

- **Nothing is shown for an organisation until its access is confirmed.** Organisation data, including the analyses list, renders only after the person's membership for the active organisation is confirmed. Until then the page shows a neutral loading state with no text, and never the organisation's data.
- **The organisation name appears only once it is confirmed.** Until then the name slot in the header is empty and the layout does not shift. A placeholder name is never shown.
- **Edge colours stay with edges.** No colour is used for interface state that the edge colours carry. Blue and vermillion are reserved for edge direction, and interface state uses text, shape or neutral colour. The focus ring and the destructive rule are affordances, not interface state; they may use blue and vermillion respectively, without carrying edge meaning.
- **Destructive actions use ink text.** A destructive action is marked by its label and a 3px vermillion rule, with ink text, never with coloured text on a light surface.
- **A confirmed membership stays confirmed on refresh.** A refresh on an organisation the person belongs to shows that organisation straight away. The "organisation syncing" message appears only while a membership is being written: after creating an organisation, or accepting an invitation.
- **Switching keeps the session.** A switch never asks the person to sign in again, and never reports an expired session while the session is valid. Before an organisation's data is requested, a token for that organisation is obtained.
- **One session per sign-in.** An organisation is a choice inside the person's session. Switching organisations does not create a session.
- **An invitation grants nothing until it is accepted.** A pending invitation confers no access and creates no membership. Accepting creates the membership through the webhook path. Declining creates nothing.
- **An invitation belongs to one email address.** Invitations are shown only to the signed-in account whose verified address matches the invited address. The person is never asked to type an email address to find one.
- **A wrong account gets a clear answer and no detail.** A signed-in account with no matching invitation is told so. It sees nothing about the organisation the invitation was for.
- **A declined invitation stays declined.** It is not shown again to that person. A new invitation from an admin for the same organisation is a new decision, and shows again.
- **Icon-only controls have accessible names.** A tooltip alone is not an accessible name. Every icon-only control, including the theme control, has a name that a screen reader announces. The theme control's name states the current theme and that activating it changes the theme.
- **The badge follows interface rules.** The Invitations badge is interface state, so it uses ink and text, never blue or vermillion.
- **Organisation creation happens once.** A double press, two open tabs, or two browsers must not create two organisations from one request. The server returns the same organisation for the same idempotency key, and creates a new one only for a new key. In addition, a request for an organisation with the same name as one the same person created in the last 10 seconds returns that organisation instead of creating another. After 10 seconds, the same name creates a new organisation.
- **Only the owner deletes.** The owner is the person recorded as the creator. Deletion is refused for anyone else, and refused when it would leave the person with no organisation.
- **Deleting an organisation removes its data.** Its rows are removed from every table, and no one can read them afterwards.
- **Admins manage, the owner deletes.** Admins, including the owner, can invite, revoke invitations, remove members and rename. Only the owner can delete.
- **The owner cannot be removed or demoted.** No one, including an admin, can remove the owner from the organisation or change the owner's role. The server refuses these requests, whatever the interface shows.
- **Only the owner promotes and demotes.** An admin who is not the owner cannot promote or demote anyone.
- **Admin deletion through the browser is an accepted risk.** The admin role carries the identity provider's organisation delete permission. Clerk does not allow it to be removed from the creator's role, and custom roles are not used, so an admin could call the identity provider's delete directly from the browser. This is accepted for these reasons: admins are elevated only by the owner, after the owner trusts them; and deletion still removes the organisation's data through the webhook. Nothing in the acceptance check tests this path, and it must not be treated as a guarantee.
- **Role checks use the identity provider's values.** The owner and admin checks read the role from the verified token, using the exact value the identity provider issues. That value is confirmed with a live token before the check is written.
- **Nobody is left without an organisation.** Removal from an organisation leaves the person in their personal organisation or another organisation they belong to.
- **Existing accounts are brought up to the rule.** An account created before this rule receives a personal organisation at its next sign-in, if it owns no organisation.
- **Earlier constraints still hold:** the token check, the organisation check, the membership webhook and its retry, prepared statements off, the sync role's narrow rights, one connection factory, one session mechanism, configuration that fails loudly, and no table beyond those named in later phases.

## Acceptance check

1. Sign up with a new account. It lands in an organisation of its own, named by the naming rule, and that organisation is active.
2. Create a second organisation with a name you enter. It becomes active, and you are its owner.
3. Invite another account by email. Sign in with that account. The invitation appears on arrival, with the organisation's name and who sent it. You are not asked to type an email address.
4. Use the invitation link while signed in with an account that was not invited. The page says no invitation exists for this account and tells you to sign in with the invited address. It shows no organisation details.
5. Accept one invitation, from the root page and from the invitations page. The pending list and the switcher update at once, the organisation appears in the switcher, and it is not active until you switch to it. Decline another. It does not come back on refresh.
6. Switch between organisations from the root page and from the invitations page. Each switch opens that organisation's root, with no sign-in prompt, no reload, and no expired-session message.
7. Refresh while on an organisation you belong to. Its analyses appear, with no "organisation syncing" message.
8. Before an organisation's access is confirmed, none of its analyses is visible on the page, and the header shows no organisation name.
9. As an admin, including the owner, invite someone, revoke a pending invitation, rename the organisation, and remove a member. The header shows the new name straight away after the rename. As a plain member, none of these controls is shown.
10. As an admin who is not the owner, deletion is not offered, and the server refuses a deletion request made through the application. As the owner with another organisation available, deletion succeeds and the organisation's data is gone. As the owner with no other organisation, deletion is refused and the page gives a reason.
11. Remove someone from an organisation. Their next request for that organisation is refused, and they still have their personal organisation.
12. Sign in with an account created before this rule. It receives a personal organisation.
13. As the owner, promote a member to admin, then demote them back to member. Each change takes effect on the person's next request.
14. As an admin who is not the owner, try to demote the owner, or remove the owner. Both are refused, and the owner keeps their role and their membership.
15. Use the Invitations control in the header from the root page and from an organisation's page. It opens the invitations page each time.
16. Click the organisation's name in the top left from the invitations page. It opens the root of the current organisation.
17. After accepting or declining an invitation, the Invitations badge's count falls straight away, and the badge disappears when none remain.
18. Each icon-only control, including the theme control, is announced by a screen reader with a name that matches its current state.

## Review

Before this phase is reported as complete, a separate review pass checks the built code against every Build item, Constraint and Acceptance check in this document. The review reports each item as met, partly met or not met, with the file and line. Any item not met is fixed before the phase is reported complete.

## Not in this phase

Transferring ownership. Custom roles. Resuming the last page within each organisation, which is deferred until analyses can be opened. Invitation expiry settings beyond the default. Styling beyond the existing shell.
