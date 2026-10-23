# Person 3 release pipeline handoff

## What is implemented

PR/push CI runs application tests with an 80% application line-coverage gate,
release-script tests, and a disposable Docker deployment/rollback exercise.
Evidence is uploaded for 14 days. `requirements-ci.txt` contains coverage tooling.

`release.yml` runs automatically on every push to `main`, including merged pull
requests, and can still be started manually from the Actions tab. It is disabled
unless the repository variable `RELEASE_ENABLED` is exactly `true`. The workflow
builds/pushes once, records the image digest, deploys that image on Test EC2, runs
acceptance suites, then promotes it to Production EC2. Production has no additional
manual approval once the run passes tests.

The whole release holds a concurrency lock without cancelling an active run.
GitHub may replace an older pending run with a newer pending run. Do not manually
cancel a deployment: process termination or a server outage can interrupt recovery.

## Person 1: servers

- Linux x64 test and production EC2s, Docker Engine and Compose v2, Python 3.10+
  (with venv/pip support), Git, and the runner service installed and running.
- Runner labels: `self-hosted`, `linux`, `x64`, plus `taskmanager-test` on test
  and `taskmanager-production` on production. Never assign both labels to one host.
- Runner user needs Docker access and a persistent, writable directory:
  `/opt/taskmanager/test` or `/opt/taskmanager/production` (outside checkout).
  These directories must be created by the administrator, owned by the runner
  user and restricted to that user. Docker access is privileged.
- The servers need outbound HTTPS for GitHub, Docker Hub, package installation
  and artifact upload; RDS access on 5432; production application ingress on 80.
- Separate PostgreSQL databases/users, with each user limited to its own database.
  Initial table creation is performed by the app, so grant the needed schema permissions.
- Person 4 supplies the installed browser/driver requirements for headless Selenium.
- Keep both runners online for commissioning. A job waiting for an offline runner
  is not bounded by the step execution timeout; check runner status before dispatch.

## Repository variables and secrets

Use Settings > Secrets and variables > Actions. This version uses repository
secrets because private-repository environment protection may be unavailable on
the current plan. Separate names provide configuration separation, not a security
boundary against someone who can change workflows. Only trusted code may run on EC2.

| Type | Name | Value |
| --- | --- | --- |
| Variable | `RELEASE_ENABLED` | Leave unset/false until commissioning prerequisites are complete |
| Variable | `DOCKERHUB_IMAGE` | `namespace/repository`, no tag or protocol |
| Variable | `DOCKERHUB_USERNAME` | Docker Hub username |
| Secret | `DOCKERHUB_TOKEN` | Token with push access to that repository |
| Secret | `DOCKERHUB_PULL_TOKEN` | Token with pull access, including for public-image authenticated pulls |
| Secret | `TEST_DATABASE_URL` | Test PostgreSQL URL; percent-encode reserved password characters |
| Secret | `TEST_SECRET_KEY` | Random Flask key for test |
| Secret | `PROD_DATABASE_URL` | Production PostgreSQL URL, using a different database/user |
| Secret | `PROD_SECRET_KEY` | Separate random Flask key for production |

Never put credentials in Git, issue bodies or screenshots. The compose file requires
`IMAGE_REF`, `BUILD_ID`, `DATABASE_URL`, and `SECRET_KEY`; port defaults to 80.
The `host.docker.internal` mapping supports the disposable local database check;
AWS uses the RDS endpoint in the supplied URL.

## Check Docker Hub access before AWS setup

After the workflow is reviewed and merged to `main`, open Actions >
Docker Hub - Check access > Run workflow and select `main`.
It pushes a `connection-check-<run>-<attempt>` image, then a fresh runner logs
in with the pull token and downloads the same digest. Both jobs must pass.
The run summary records the digest. This verifies authentication and push/pull
operations, not that the pull token lacks write permission; check that in Docker Hub.
The test image remains in Docker Hub and has the repository's visibility.
No `latest` or release tag is changed, and AWS deployment stays disabled.

## Person 4: acceptance-test contract

Supply `requirements-e2e.txt`, `tests/integration/test_*.py` and
`tests/e2e/test_*.py`. Missing suites block the release before publication.
Use `BASE_URL` (test server), `EXPECTED_BUILD_ID`, and `DATABASE_URL` (test only).
Tests must exercise the running digest's application over HTTP and verify its build
ID, rather than testing only imported source. PostgreSQL-specific checks may also
use the test database. Use unique records and cleanup; never drop the shared schema.

Commands run as separate pytest processes to keep SQLite unit-test configuration
out of PostgreSQL/browser tests. Nonzero exit, no collected tests or any skipped
mandatory case blocks production. Write browser screenshots/other diagnostics to
`reports/`. No placeholder suite is supplied and no skip bypass is permitted.

## Deployment and recovery

Run `python3 -m scripts.deploy --environment production --state-dir
/opt/taskmanager/production` with configuration in the process environment.
The script pulls before replacement, checks the running Docker image ID,
waits for `/health` to report the expected build, reads the board, then creates,
reads and deletes one uniquely named smoke task. Cleanup is attempted after failure
too. Failed cleanup also fails the smoke test.

`current.json` records only a verified image/build; `previous.json` snapshots it
before replacement. A failed candidate restores and verifies the previous image,
but exits nonzero even if recovery succeeds. First-release and failed recovery
require intervention. An existing manually installed app is not automatically
adopted as a known-good release: commission the first deployment accordingly.

`report.json` records candidate, previous release and outcome. Failed-container logs
are captured before rollback, with configured credentials redacted. Keep all
application logs free of secrets as well. The workflow retains these reports/logs.
Image rollback reuses current environment settings and does not undo database
changes. Keep schema changes compatible; credential/configuration rollback is manual.
One production container means a short interruption during replacement is expected.

Failed release runs create a GitHub issue with a run link and job results. Team members
must subscribe to repository issues and enable GitHub notifications, then verify
delivery with a controlled failure. Issue creation failure remains visible as a
failed notification job. This does not replace Person 4's CloudWatch alarm delivery.

## Local validation

Run `python -m scripts.check_pipeline` with Docker Desktop running (or Linux Docker
with Compose). It creates a local registry, PostgreSQL and isolated app deployment;
pushes images only to the local registry; tests success, a genuinely broken image,
rollback and first-release failure; then removes its containers and database volume.
It needs ports 15000, 15432 and 18080 free. The disposable PostgreSQL port is published
on the host to allow access from the app container: run this on a trusted machine.
Local test images/build cache remain for reuse. Reports go to `reports/container-check/`.

## Automatic merging

The public repository enforces the `Protect main` ruleset. Team PRs do not require
a reviewer approval, but all three required CI checks must pass before merging.

- Push changes to a separate branch and open a non-draft PR targeting `main`.
- `auto-merge.yml` enables auto-merge for the four listed team accounts when the
  branch belongs to this repository and the author still has write access.
- GitHub waits for Run Flask Tests, Build Docker Image, and Integration and
  Selenium Tests. The branch must be up to date and review conversations resolved.
- Drafts and fork PRs are excluded. Conflicts or an outdated branch may require
  a developer to update the branch; the workflow does not update branches itself.
- `AUTO_MERGE_TOKEN` enables merging so the resulting push triggers Release.
  Keep this repository secret valid and renew it before its expiry.

After merging, Release publishes the Docker image, tests it on Test EC2, and
deploys the same digest to Production. Failed release tests block production;
failed production verification attempts rollback to the previous verified image.

## Commissioning checklist

1. Confirm all required CI checks pass before changes merge to `main`.
2. Configure variables/secrets, start both runners, and verify RDS connectivity.
3. Verify a team PR automatically merges after its required checks pass and
   that the resulting push starts Release.
4. Set `RELEASE_ENABLED=true`, dispatch the release from main, and verify the
   production build, data persistence, evidence and notification delivery.
5. Exercise blocked tests, failed deployment, successful rollback, first-release
   failure and failed recovery in disposable infrastructure before the demo.
6. Only after commissioning, merge the `push` trigger on main. To pause automatic
   releases at any time, set `RELEASE_ENABLED` to `false`.

Useful official references:
- https://docs.github.com/en/actions/concepts/workflows-and-actions/concurrency
- https://docs.docker.com/build/ci/github-actions/
- https://pytest-cov.readthedocs.io/en/latest/config.html
