# Workshop Registry review policy

## Permanent identity

A module ID is permanently associated with its reviewed HTTPS GitHub
repository, publisher, and official/community status. Normal pull requests
cannot transfer ownership, delete an existing module, reorder versions, or
rewrite any historical release identity, byte count, digest, compatibility
range, or permission declaration.

An ownership transfer is an exceptional maintainer operation outside the
normal PR path. It requires evidence from both owners, an incident/transfer
record, CODEOWNER review, and a separately announced Lumina trust update.
The v1 tooling rejects all normal-PR transfer flags.

### GitHub URL redirects

GitHub may redirect a reviewed repository URL after a rename or transfer.
Scanning and release inspection follow bounded redirects inside the HTTPS
GitHub API. A changed asset URL is accepted only after repository metadata
requested through the registered address confirms the current canonical
repository and a valid numeric repository ID. Downloads still use the
registered release identity, are fetched twice, and retain exact byte/digest
and manifest checks.

Routing does not rewrite source records, publisher/official status, or signed
history, and does not authorize an ownership or trust change. Newly discovered
versions remain proposals requiring the existing maintainer review, signing,
and publication controls. An actual trust transfer still follows the
exceptional process above.

## New versions

Every added version must point to one non-draft, non-prerelease tag and one
exactly named `.lumina-workshop` asset. CI downloads the asset twice, requires
stable bytes, verifies both archive and exact manifest SHA-256 values, and
performs the full static package inspection without extracting or executing
module code.

Permission and compatibility changes are visible source diffs. An automated
scanner may append a candidate in a PR, but it cannot merge, sign, or publish
the Registry. Permission expansion, compatibility expansion, new executable
entry types, and ownership changes always require maintainer review.

## Blocking a release

An existing version may move to `blocked` only with a complete revocation
record containing a stable reason code, severity, and bilingual message. All
other historical fields remain byte-for-byte immutable. Blocked versions are
never installation candidates.

## Required repository controls

Protected `main` requires passing CI, CODEOWNER approval for `modules/`,
`schemas/`, and `.github/`, and dismissal of stale approvals. The
`registry-production` Environment requires a reviewer and alone holds the
signing secret. Pull-request and scanner jobs never receive that secret.
