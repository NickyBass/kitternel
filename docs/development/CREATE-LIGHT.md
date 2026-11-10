# Create a standalone Light application

From a Kitternel Git checkout, using Python 3.11+ and Git:

```sh
python3 scripts/create-light.py garden-notes ../garden-notes
cd ../garden-notes
```

The destination parent must already exist. The destination itself must not exist, even as an empty directory or dangling symlink, and must resolve outside the source repository. Names are lowercase ASCII letters/digits, beginning with a letter, with single internal hyphens, at most 32 characters. Rust keywords, names conflicting with direct Rust dependencies or standard-library crates, and Windows device names are rejected. The script does not execute project names as shell commands, install dependencies, initialize Git, or start containers.

The generator reads the current working-tree content of tracked template files, plus an explicit list of smoke runners, the canonical CI workflow, Git attributes/ignore rules, and the MIT license. It does not copy untracked files, node_modules, target directories, databases, or local .env files. Use a trusted, reviewed checkout: tracked source changes are deliberately included. Source symlinks are rejected. Generation is staged before exclusively claiming the new destination; failures do not replace existing destinations. No existing application or migration history is rewritten.

## Generated layout and customization

```text
backend/       # Rust/Axum, SQLx migrations, tests, pinned toolchain/lockfile
frontend/      # React/TypeScript, unit/browser tests, pinned Node/lockfile
scripts/       # Native/browser/Docker/recovery runners and focused regressions
Dockerfile
compose.yaml
.github/workflows/ci.yml
README.md
AGENTS.md
CONTRIBUTING.md
SECURITY.md
LICENSE
```

For `garden-notes`, Cargo package/binary and Docker image are `garden-notes`, Rust imports are `garden_notes`, frontend package is `garden-notes-frontend`, display name is `Garden Notes`, and Compose project is `garden-notes`. The database is `/data/garden-notes.db`. Compose volume identity includes the project name; keep it stable after deployment. Numeric UID/GID, security settings, pool limits, routes, and architecture are preserved. The container uses a fixed neutral `app` account at UID/GID 10001 so project names cannot collide with built-in OS accounts.

Identity changes use known first-party file mappings and whole-token substitutions in one pass. npm metadata is updated as JSON; the single local Cargo lockfile package is updated explicitly. Unknown upstream identity/layout references fail generation rather than silently producing a partially adapted project. Keep the mapping and regression coverage updated when changing the template. The Linux process-name assertion accounts for the kernel's 15-byte comm limit.

The output includes independent development, contribution, security, AI-agent, Docker/Compose, and recovery instructions. It does not include the original repository roadmap, setup prompts, platform guides, source Git history, or generator. The upstream MIT notice is retained; configure your own security contact, support policy, and project repository. There is no inherited claim of production readiness or successful deployment.

## Run the new project

Follow its README. From the generated root:

```sh
docker build -t garden-notes:local .
docker compose up -d --no-build --wait
```

Or install the pinned toolchains, build `frontend`, and run Cargo from `backend`. Generated smoke runners use only generated files, and honor Cargo target-directory configuration. A new Git repository can use the included GitHub Actions workflow without Kitternel.

To test the generator itself from the source repository:

```sh
python3 scripts/test-create-light.py -v
```

Step 3 verifies extraction, names, safety, file completeness, and selected native/frontend checks in a temporary generated project. Step 4 will perform a clean generated-image build and Docker/Compose persistence, health, shutdown, and recovery verification. Commands shown above are instructions, not evidence that those deployment checks have already passed.
