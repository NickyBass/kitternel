# Alpha preparation validation

Step 8B, 2026-11-13. Source baseline:
`0214e52317d74fac3c7d8f2d120f6711da51377d` (merged PR #13).
Changes are documentation and original static diagram assets only. Full Step 8A
report/evidence files are absent from this replacement environment; see the
[risk register](ALPHA-LIMITATIONS.md) for provenance limits.

## Scope

The root README is the starter's landing page. Root technical details were retained
in [LIGHT-REFERENCE.md](../development/LIGHT-REFERENCE.md). The generator continues
to supply its own documentation templates; the new branding/release documents are
not copied into generated applications. Source code, generator behavior, lockfiles,
Docker/Compose, migrations, tool pins and CI gates are unchanged.

## Executed checks

| Command | Result |
| --- | --- |
| `python3 scripts/test-create-light.py -v` | PASS: 13 executed regressions, optional Rust formatting integration skipped; 14 discovered |
| `python3 scripts/check-toolchain-pins.py` | PASS: offline current declaration relationships |
| `python3 scripts/test-toolchain-pins.py -v` | PASS: 21 tests |
| `git diff --check` | PASS at documentation review; repeated before commit |
| XML parsing of `docs/assets/architecture.svg` | PASS: static SVG, no script/font/network dependencies |

The generated application's own pin checker, link/anchor checks, Docker quick-start
and local theme/viewport preview are recorded in the final preparation results below.
No fresh vulnerability-free claim is made by these documentation checks.

## Verification boundaries

Full Rust lint/unit/process and frontend unit/browser suites are not independently
re-run for documentation/static-only changes. A fresh generated Docker quick-start
compiles the backend and typechecks/builds the frontend; it verifies the public
onboarding commands, not every runtime behavior or every historical audit claim.
No scanner version/dependency upgrade, suppression or threshold change is justified
by this task. Publication still requires fresh candidate scans and the maintainer's
risk review. GitHub settings and production deployments are not changed or tested.

The GitHub private-vulnerability-reporting REST probe returned 404. It does not
verify a working private reporting channel. A local Markdown preview, even using
GitHub's Markdown renderer, is not proof of actual GitHub UI, browser auth,
social-preview configuration or theme behavior on every client.

## Final preparation results

- **Links/assets:** `python3 /tmp/step8b-validation/check-docs.py` checked relative Markdown targets and heading anchors in root
  README/SECURITY/START-HERE, the retained technical reference and release docs;
  no missing targets/anchors found. CONTRIBUTING now points to the relocated
  runtime-configuration reference. Original SVG parsed successfully and contains
  only local static vector/text content; essential architecture is also prose.
- **Rendering:** `gh api markdown -f mode=gfm -f context=NickyBass/kitternel
  -F text=@README.md` rendered successfully. Chromium/Playwright inspected this
  output with a local approximate GitHub stylesheet in light/dark at 1280 and
  375 CSS pixels: no document overflow, failed images or page errors. This is
  local preview evidence, not an actual GitHub UI/mobile-client guarantee.
- **Fresh quick start:** cloned `https://github.com/NickyBass/kitternel.git` into a
  disposable directory, then ran `python3 scripts/create-light.py garden-notes
  ../garden-notes`. Generation passed with own lockfiles and Docker configuration.
  `python3 scripts/check-toolchain-pins.py` also passed in the generated app.
- **Build/start:** from the generated root, `docker build --secret
  id=proxy_ca,src="$CODEX_PROXY_CERT" -t garden-notes:local .` and
  `docker compose up -d --no-build --wait` passed. The documented optional CA
  adapter was used for the managed TLS proxy; the Dockerfile was unchanged and
  TLS verification remained enabled. `curl --fail
  http://127.0.0.1:8080/health/ready` returned `{"status":"ready"}` and
  `/api/hello` returned `{"message":"Hello from Garden Notes."}`. No preexisting
  database was supplied. A subsequent fresh-clone image build reused layers;
  no all-layer-uncached claim is made.
- **Storage/identity:** generated app ran as UID/GID 10001. In-container
  `sqlite3 -readonly /data/garden-notes.db 'PRAGMA integrity_check; SELECT
  version,success FROM _sqlx_migrations;'` returned `ok` and `1|1`. Tested image ID: `sha256:4a9ebca8d46ada142f17a960d21962f5416440926af9b3dce306aca540e91f01`. Application
  Docker build/runtime received only generated files, no Kitternel checkout mount.
- **Pebble:** a fresh generated image still contained `/usr/bin/pebble` and
  `dpkg-query -S /usr/bin/pebble` reported no owner. This inventories presence,
  not exploitability or a new CVE scan. The risk register retains uncertainty.
- **Cleanup:** stopped/removed only the disposable quick-start Compose project,
  its network and newly created test volume. No deployment data was used. The
  destructive volume cleanup was specific to this owned disposable fixture, not
  a recommended deployment/update command.
- **Hygiene:** bounded changed-document search found no obvious provider-token,
  private-key or personal absolute-path patterns. Root LICENSE is unchanged;
  generator regressions cover retained generated license notice. This is not
  full Git history or transitive license clearance. No ownership/history rewrite.
- **Hosted baseline:** GitHub REST reported successful CI, generation and Security
  runs for source baseline `0214e52317d74fac3c7d8f2d120f6711da51377d`.
  New PR check conclusions must be inspected separately; no fresh scan results
  are implied by historical run status or by this docs-only PR.

Initial fixture setup attempts failed when a build was invoked from the source
root (which has no root Dockerfile) and generation encountered an existing test
destination. Those setup errors are not passing attempts; the subsequent isolated
fresh-clone sequence above completed successfully. No source correction was needed.

## Remaining review item: supplied logo

The green/magenta wordmark is visible in the task conversation, but its original
PNG bytes are not available among the uploaded workspace files. Do not reconstruct,
redraw or silently substitute it. The README retains an accessible text hero and
original static architecture diagram without a broken image reference. This PR
stays a draft until the original PNG can be copied unchanged as a local asset and
its light/dark rendering checked. The social-preview upload remains a separate
manual maintainer action; no repository setting was changed.
