# Public alpha publication checklist

For maintainers preparing `v0.1.0-alpha.1`. **Recommendations and pending actions,
not settings already applied.** This documentation PR must not publish, merge,
tag, change visibility or configure repository settings automatically.

## GitHub presentation

- [ ] Description: “An independent, Docker-first full-stack starter powered by
  Rust, React and SQLite.”
- [ ] Suggested topics: `rust`, `axum`, `react`, `typescript`, `sqlite`, `sqlx`,
  `vite`, `tailwindcss`, `docker`, `starter-template`, `full-stack`.
- [ ] About: link to the README/docs in this repository; do not invent a live
  website, demo deployment or support endpoint. Show relevant topics/releases.
- [ ] Keep the supplied Kitternel logo as the wordmark. Verify ownership/permission
  to distribute it and its intended scope under the repository license.
- [ ] Social preview: prepare/upload an original 1280 × 640 PNG/JPEG with the logo,
  restrained navy background and short Rust/React/SQLite description. Check GitHub's
  current upload limits, crop and contrast. A README asset alone does not set the
  repository's social preview; no preview upload is performed by this PR.
- [ ] Confirm GitHub detects the root MIT LICENSE, preserve its attribution in
  generated source and review third-party distribution obligations if binaries or
  images are later distributed. Do not imply MIT relicenses dependencies.

## Privacy, identity and reporting

- [ ] Confirm the Kitternel name/identity and any necessary name/trademark checks.
- [ ] Review intended public history, Git author name/email metadata, historical
  planning instructions, branches and artifact contents. Bounded working-tree
  checks do not certify all historical objects. Do not rewrite history in this PR.
- [ ] Verify no unintended credentials, private paths, database copies, local
  configuration or build artifacts enter the publication. Resolve any confirmed
  secret before publication using a separately reviewed response.
- [ ] In repository Settings → Security, enable private vulnerability reporting
  where available and verify the reporter flow; otherwise establish a verified
  private channel and update SECURITY.md. Do not publish a made-up address or send
  exploit details through a public issue. The preparation REST probe returned 404,
  not proof that the feature is enabled or unavailable to all maintainers.
- [ ] Confirm SECURITY.md's alpha support expectations. Generated owners must
  configure their own contact and maintenance policy.

## Branches and required checks

- [ ] Confirm default branch `main` (observed during preparation). Generated owners
  using a different branch must adapt their own security push filter.
- [ ] Review branch protection/rulesets for `main`: require PR review, passing
  relevant checks and resolved conversations; restrict bypass/force pushes as
  appropriate for maintainers. Exact available rules depend on repository plan.
- [ ] Inspect actual check names before requiring them: CI `light`, generation
  `generate` / `standalone-docker`, security `dependencies` / `docker`. Ensure path
  filtering does not leave a required check permanently pending on docs-only PRs.
  Require the applicable validation without changing gates in this PR.
- [ ] Decide whether optional Code Scanning is supported before setting
  `ENABLE_CODE_SCANNING=true`; artifact reports are the default. Verify artifact
  access/retention rather than assuming optional SARIF upload ran.

## Candidate and risk review

- [ ] Recover/archive the complete Step 8A report and evidence ZIP; they are absent
  from the replacement workspace. Read [known risks](ALPHA-LIMITATIONS.md) and the
  [preparation validation](PREPARATION-VALIDATION.md) without merging dates/scopes.
- [ ] Record exact release source SHA, tested image ID/digest, platform, scan dates,
  scanner/database versions and links to CI/artifacts for that candidate.
- [ ] Re-run required generation/build/runtime/recovery and fresh security checks
  against the exact candidate; do not interpret an incomplete scan as passing.
- [ ] Review SQLx Git pin, minimatch override, runtime vendor findings and Pebble
  provenance/applicability. Keep findings visible; no blanket suppressions.
- [ ] For each remaining accepted risk, record owner, next review date, evidence
  link and treatment rationale in the release review. HIGH/CRITICAL findings need
  evidenced resolution, not an unsupported dismissal.
- [ ] Check alpha notes state Linux/amd64 validation, single-instance local SQLite,
  missing auth, compatibility limits and generated-owner maintenance obligations.
- [ ] Verify fresh clone/generation instructions and logo/link rendering on actual
  GitHub in both themes and a narrow viewport. Local preview is supporting evidence.

## Publication — manual, after approval

- [ ] Review/merge the preparation PR only after maintainer approval; this task does
  not merge it. Recheck candidate validation if source changes afterward.
- [ ] Decide on repository visibility only after naming/privacy/security review.
  No visibility change is implied by preparing a public README.
- [ ] Create `v0.1.0-alpha.1` at the reviewed release SHA using the maintainer's tag
  signing policy. This preparation creates no tag.
- [ ] Create the GitHub Release using [prepared notes](v0.1.0-alpha.1.md), mark it
  **pre-release**, record the actual date/SHA and disclose known limits. Never
  describe it as production-certified or automatically maintained.
- [ ] Publishing npm/crates/packages/images is a separate decision and is not
  required for this source starter alpha. No such publication is performed here.
