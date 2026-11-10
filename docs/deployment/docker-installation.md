# Install Kitternel Light with Docker, step by step

This guide takes you from a downloaded repository to a working local Kitternel
application. You do not need to know Rust or install a database server. Docker
builds the Rust backend and React frontend, then runs both in one container.

The result is a local installation at **http://localhost:8080**, with SQLite data
kept in a persistent Docker volume. This is a first installation guide, not a
public production deployment procedure. Authentication and authorization are not
implemented yet. For technical details, see the [Docker reference](docker.md).

## Before you begin

You need:

- Access to the Kitternel GitHub repository. While it is private, your GitHub
  account must have permission to read it.
- Git, Docker, and the Docker Compose plugin available in your terminal.
- An internet connection for the first build and enough disk space for downloaded
  images, build dependencies, and application data. The first build takes longer
  than later builds; duration depends on the machine and connection.

Rust, Cargo, Node.js, npm, and SQLite do **not** need to be installed on your
computer for this Docker workflow. Python is optional and used only for the
automated checks in step 8.

Use **PowerShell** on Windows and **Terminal with Bash or Zsh** on Linux/macOS.
Commands labeled `sh` below also work in PowerShell unless a separate PowerShell
example is provided. Copy commands without the surrounding Markdown fences.
Run one command at a time; if it fails, resolve the error before continuing.

### 1. Install and start Docker

Follow the official instructions for your operating system:

| Computer | Installation instructions |
| --- | --- |
| Windows | [Docker Desktop for Windows](https://docs.docker.com/desktop/setup/install/windows-install/). Use the Linux containers backend; follow Docker's WSL 2 and virtualization prerequisites. |
| macOS | [Docker Desktop for Mac](https://docs.docker.com/desktop/setup/install/mac-install/). Select the installer matching your processor. |
| Linux | [Docker Engine](https://docs.docker.com/engine/install/), using the instructions for your distribution, including the Compose plugin. Docker Desktop is another option. |

Install Git from [Git's installation guide](https://git-scm.com/book/en/v2/Getting-Started-Installing-Git)
if it is missing. Open a new terminal after installation. On Windows/macOS, start
Docker Desktop and wait until its engine is running. On Linux, ensure the Docker
service is running and your account has authorized access to it, following your
installation guide.

Check the tools:

```sh
git --version
docker version
docker compose version
docker info --format '{{.OSType}}/{{.Architecture}}'
```

`docker version` must show both **Client** and **Server** information. A Client
section followed by a connection error means Docker is not ready. The final
command must report a Linux engine. Use `docker compose` with a space, rather
than the older `docker-compose` command.

Kitternel has been exercised on Linux/amd64 and on Windows using Docker Desktop's
Linux/amd64 engine. Instructions for macOS are provided, but a macOS installation
and ARM builds have not been verified by this project. See the
[verification record](../development/verification.md).

### 2. Download the project

In your terminal, move to the folder where you want to keep the source code. A
normal local development folder is suitable; the source folder is separate from
the Docker volume that will contain your database.

```sh
git clone https://github.com/NickyBass/kitternel.git
cd kitternel
git rev-parse --short HEAD
```

If Git requests authentication, complete its normal GitHub sign-in process. Do
not put a token or password into the clone URL, a script, or an AI prompt.
`Repository not found` can mean your account lacks access to this private
repository; it does not necessarily mean the URL is wrong.

If the repository is already cloned, open that checkout instead of cloning over
it. Run `git status` and inspect any existing work before updating it.

You are now in the **repository root**: the folder containing `README.md`,
`AGENTS.md`, and `templates`. Keep the reported commit identifier if you want to
record exactly which source you installed.

### 3. Build the application image

**Working directory: repository root.**

```sh
docker build -t kitternel-light:local templates/light
```

This downloads the versions of Node and Rust pinned in the Dockerfile, installs
locked dependencies, compiles the frontend and backend, and packages the runtime.
`kitternel-light:local` is the name given to the resulting image. The last argument,
`templates/light`, is the build context; do not replace it with `.`.

Wait for the command to finish successfully. Check that the image exists:

```sh
docker image inspect kitternel-light:local --format '{{.Id}}'
```

A long image identifier is expected. Building creates an image; it does not yet
start the application. If a build fails, inspect the first failing step rather
than starting an old image and assuming the new build worked.

### 4. Start Kitternel

```sh
cd templates/light
docker compose -p kitternel-local config --quiet
docker compose -p kitternel-local up -d --no-build --wait
docker compose -p kitternel-local ps
```

**Working directory from this point through step 7: `templates/light`.**

The configuration check normally prints nothing on success. The startup command
creates the container and a persistent database volume, runs migrations, and
waits for the application's health check. `-d` keeps the application running in
the background; `--no-build` uses the image you built in step 3. `ps` should show
the `app` service running with a **healthy** status and port
`127.0.0.1:8080->8080/tcp`.

We use the explicit Compose project name `kitternel-local` throughout this guide.
Keep using the same `-p kitternel-local` option for this installation, including
after moving or renaming the source folder. The default data volume for this
project is `kitternel-local_light-data`. Changing the project name selects a
different volume and can make an existing database appear to be missing.
If you already have an installation under another project name, identify and
reuse that project and its actual volume before starting anything new.

If port 8080 is already occupied, follow [Change the local port](#change-the-local-port)
below, then repeat the startup command.

### 5. Open the page and verify the API

Open **http://localhost:8080** in a browser on the same computer that runs Docker.
The page should display:

- `Backend ready · SQLite connected`
- `Hello from Kitternel Light.`

The greeting comes from SQLite through the real backend API. Check the endpoints
as well.

**Windows PowerShell:**

```powershell
Invoke-RestMethod http://127.0.0.1:8080/health/live
Invoke-RestMethod http://127.0.0.1:8080/health/ready
Invoke-RestMethod http://127.0.0.1:8080/api/hello
```

PowerShell displays the JSON properties as objects. **Linux/macOS:**

```sh
curl --fail http://127.0.0.1:8080/health/live
curl --fail http://127.0.0.1:8080/health/ready
curl --fail http://127.0.0.1:8080/api/hello
```

Expected JSON responses, in the same order:

```json
{"status":"ok"}
{"status":"ready"}
{"message":"Hello from Kitternel Light."}
```

Liveness confirms that HTTP responds. Readiness also queries SQLite. A running
container alone is not proof that the application or database is ready.

The port is bound to `127.0.0.1`, so this guide does not expose the app to your
network or the internet. If Docker is on a remote server or in an AI cloud
environment, your own browser's `localhost` points to your own computer. Use an
approved SSH tunnel or environment preview; do not change the binding to a public
interface just to work around that distinction.

### 6. Inspect logs, stop, and start again

```sh
docker compose -p kitternel-local logs --tail 100 app
docker compose -p kitternel-local stop
docker compose -p kitternel-local up -d --no-build --wait
```

`stop` shuts down the application and keeps its database. The next `up` reuses
that database. Closing the terminal does not stop a detached container. Docker
Desktop must remain running for the application to be reachable.

The configured `unless-stopped` policy restarts an exited container when
appropriate, including after the Docker engine starts again, unless you stopped
it explicitly. An unhealthy status alone does not trigger a Docker restart.

If you want to remove this installation's containers and network while keeping
its data:

```sh
docker compose -p kitternel-local down
```

A later `up` recreates the container using the retained named volume. **Do not add
`--volumes` or `-v` to `down`** unless you deliberately intend to delete this
installation's database. Do not use broad Docker volume cleanup commands to fix
a startup problem. A persistent volume protects against container replacement;
it is not a backup against disk loss or accidental deletion.

### 7. Back up before updating

Follow the [backup and restore procedure](backup-restore.md) before replacing an
image that may change the database schema. It creates a consistent snapshot,
exports it, and verifies restoration into a separate volume. Do not copy only a
live `.db` file: SQLite may also have data in WAL files.

When using that procedure with this installation, use
`docker compose -p kitternel-local` wherever it says `docker compose`. Discover
the actual `/data` mount rather than copying its example source volume name.
The backup guide's shell-variable and multiline examples use Bash/POSIX syntax;
on Windows, use an available Bash environment or ask your AI assistant to
translate them to PowerShell while preserving the same mounts and safeguards.
Do not paste Bash variable assignments directly into PowerShell.

For an upgrade, review the target revision and its migrations, verify your backup,
and return to the **repository root**. With a clean checkout:

```sh
git status
git pull --ff-only
docker build -t kitternel-light:local templates/light
```

Stop if Git reports local changes you need to preserve, a pull failure, or a build
failure. If the build succeeds, apply it from `templates/light`:

```sh
cd templates/light
docker compose -p kitternel-local up -d --no-build --wait
```

Repeat the page and endpoint checks from step 5. Compose replaces the container
when the image changes and retains the named volume. Allow for downtime. Startup
applies pending migrations, so launching an older image does not undo a schema
change and is not an automatic rollback procedure.

### 8. Optional: run the automated Docker checks

These checks need Python 3 with its standard SQLite module on the host. They do
not require a host Rust or Node installation. Run from the **repository root**,
after building the image.

**Windows PowerShell:**

```powershell
py --version
py scripts/docker-smoke.py --image kitternel-light:local -v
py scripts/sqlite-backup-smoke.py --image kitternel-light:local -v
```

**Linux/macOS:**

```sh
python3 --version
python3 scripts/docker-smoke.py --image kitternel-light:local -v
python3 scripts/sqlite-backup-smoke.py --image kitternel-light:local -v
```

The current suites report **5 Docker tests** and **6 backup/restore tests**, ending
with `OK`. They create uniquely named temporary containers and volumes, test real
HTTP requests and persistence after container replacement, and restore a snapshot
into independent storage. They clean up their own resources. Do not modify them
to use your installation's data volume. Successful local tests do not prove that
GitHub Actions or an external production deployment passed.

## Change the local port

If port 8080 is busy, open or create `.env` in `templates/light` with a text editor.
Preserve any existing entries and add or update this line:

```dotenv
HOST_PORT=8081
```

Save the file as `.env`, not `.env.txt`. Then run from the same directory:

```sh
docker compose -p kitternel-local up -d --no-build --wait
docker compose -p kitternel-local ps
```

Open **http://localhost:8081** and use port 8081 in the endpoint checks. The app's
internal port stays 8080. Keep this local `.env` for later commands. If your shell
already defines `HOST_PORT`, it takes precedence over the file; remove or update
that shell variable if Compose still uses the wrong port. See Docker's
[environment interpolation reference](https://docs.docker.com/compose/how-tos/environment-variables/variable-interpolation/).

Compose reads `.env` to substitute `HOST_PORT` in `compose.yaml`. This does not
mean that every `.env` entry is passed to the application: the backend itself
does not automatically load `.env`, and Compose explicitly sets its runtime
environment. Other runtime changes require a reviewed Compose configuration.

## When something goes wrong

Start with these commands from `templates/light`:

```sh
docker compose -p kitternel-local ps -a
docker compose -p kitternel-local logs --tail 100 app
```

| Symptom | What to check next |
| --- | --- |
| `docker` or `git` is not recognized | Install the missing tool, reopen the terminal, and repeat step 1. |
| Docker connection or named-pipe permission error | Check that Docker Desktop/the engine is running and your account/session is authorized to access it. On Windows, confirm Linux containers. |
| `unknown flag: --wait` | Update the Compose plugin using the official Docker installation route. See [`compose up`](https://docs.docker.com/reference/cli/docker/compose/up/) for supported options. |
| `no configuration file provided` | You must run Compose commands from `templates/light`, where `compose.yaml` lives. |
| `COPY` cannot find backend/frontend | Build from the repository root with `templates/light` as the context, as in step 3. |
| Port is already allocated | Follow the local-port instructions; do not stop an unrelated application. |
| Container starts but becomes unhealthy | Read the app logs and inspect storage errors, disk space, and readiness. See the [troubleshooting guide](troubleshooting.md). Do not delete the database. |
| Backup helper reports `no such file or directory` even though it is in the image | On Windows, old checkouts may have CRLF shell scripts. The repository's `.gitattributes` requires LF. Preserve local edits, restore LF line endings for the two `templates/light/scripts/*.sh` helpers, then rebuild the image. |
| Backup test reports Windows `WinError 32` during temporary SQLite cleanup | Use a revision containing the explicit SQLite connection-close fix (`e40c0ad` or later), preserving local changes before updating. |
| HTTPS certificate failure during build | Use the approved CA/proxy configuration. Do not disable TLS verification. The [Docker reference](docker.md) explains the optional build secret for managed proxy environments. |

## Install with help from an AI assistant

An assistant needs access to the terminal/filesystem of the computer where you
want Kitternel installed, plus authorized repository and Docker access. An AI
running in a remote workspace installs there unless it explicitly has access to
your computer. A text-only assistant can explain commands for you to run locally.

Copy and adapt this prompt:

```text
Help me install Kitternel Light with Docker on this computer.
Repository: https://github.com/NickyBass/kitternel.git
Installation folder: [enter my chosen local folder]
Operating system and terminal: [for example, Windows and PowerShell]
Preferred local port: 8080, or an available alternative if occupied.

Read AGENTS.md, docs/deployment/docker-installation.md, the canonical Dockerfile,
and compose.yaml before acting. Inspect existing checkouts, local changes,
Docker projects, ports, and data volumes before creating or changing resources.
If an installation already exists, identify its Compose project and actual /data
mount and preserve them. Otherwise use project name kitternel-local.

Check Git, the Docker server, the Linux engine, Compose, and repository access.
Use the canonical templates/light build context and pinned dependencies.
Do not install host Rust/Node/database tools for this Docker workflow.
Use the correct shell syntax and keep the application bound to loopback.
Run the documented build, wait for health, and verify the page and all three
HTTP endpoints. If Python is available, run the isolated Docker and backup suites.

Do not overwrite my local changes, delete data volumes, expose the app publicly,
print credentials, disable TLS checks, or push repository changes without my
explicit instruction. Diagnose errors before proposing a fix; explain any code
change and its verification. Ask before host-level changes that need my approval.

Finish with the URL, source commit, image, Compose project, actual storage mount,
start/stop commands, tests actually executed, and any remaining limitations.
Do not claim installation succeeded based only on a build or running container.
```

If you are asking for diagnosis, share the failed command and relevant sanitized
logs. Authenticate through your normal GitHub tooling; do not paste access tokens,
database contents, or private credentials into the conversation.

## Next steps

- [Docker reference](docker.md): plain Docker, proxy CA build secrets, storage
  permissions, transport limits, and shutdown behavior.
- [Backup and restore](backup-restore.md): consistent snapshots and recovery drills.
- [Troubleshooting](troubleshooting.md): detailed diagnosis without deleting data.
- [Contributing](../../CONTRIBUTING.md): native development and full test workflow.
- [Dokploy](dokploy.md) and [Coolify](coolify.md): separate platform configuration
  guides; actual deployments remain unverified.
