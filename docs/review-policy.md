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

## Module backends (manifest v2)

A module backend is Python code that Lumina runs as a local process with the
user's permissions. Static inspection checks the package shape (bounded UTF-8
`backend/` sources, wheels-only hash-pinned `pylock.toml`, no native files),
but a valid signature or a passing inspection is **not** a code review.

A maintainer who actually reviewed one exact version's backend code adds a
`backendReview` record to that source version:

```json
"backendReview": { "scope": "backend-code", "reviewer": "<github-handle>", "reviewedAt": "2026-11-04" }
```

The build binds it to that version's `sha256` and `manifestSha256`, rejects it
for packages that do not declare a backend, never attests `blocked` versions,
and publishes the list only in the separately signed `reviews-v1.json`.
`registry-v1.json` keeps its v1 format, so older hosts still parse it. Lumina
shows such versions as "reviewed"; every other community version, local
package, and GitHub install is shown as unreviewed and requires an explicit
risk confirmation. Removing a review record makes the next host refresh treat
that version as unreviewed again. A review never transfers to another version.
A review may be added to, updated on, or removed from an already published
version in a normal PR; it is review metadata, so the ownership check still
rejects every change to the release fields.

模块后端是以用户权限在本机运行的 Python 代码。签名和静态检查只证明包内容与条目一致，
不等于代码审核。只有维护者实际审核了某个精确版本的后端代码后，才在该版本记录中添加
`backendReview`；构建会把它绑定到该版本的包摘要，并只发布到单独签名的
`reviews-v1.json`，v1 目录格式保持不变。审核不随版本继承；撤回记录后宿主下次刷新即按
未审核处理。已发布版本可通过普通 PR 补充、更新或撤回审核记录；它属于审核元数据，发布字段
仍受所有权检查保护。

## Blocking a release

An existing version may move to `blocked` only with a complete revocation
record containing a stable reason code, severity, and bilingual message. All
other release fields remain byte-for-byte immutable. Blocked versions are
never installation candidates.

## Required repository controls

Protected `main` requires passing CI, CODEOWNER approval for `modules/`,
`schemas/`, and `.github/`, and dismissal of stale approvals. The
`registry-production` Environment requires a reviewer and alone holds the
signing secret. Pull-request and scanner jobs never receive that secret.
