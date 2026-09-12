# Getting started

Django Probe reports on the environment the project runs in, so it must run with
the project's dependencies installed.

## Install

Add Django Probe to the development dependencies of the project whose usage you
want to share:

=== "uv"

    ```console
    $ uv add --dev django-probe
    ```

=== "pip"

    ```console
    $ source .venv/bin/activate
    $ pip install django-probe
    ```

    Be sure to add `django-probe` to the requirements file so CI installs it too.

## Create a project token

A project token groups scheduled submissions under your organization. Generate one
from the CLI:

=== "uv"

    ```console
    $ uv run django-probe login       # approve access in your browser
    $ uv run django-probe init        # creates a project and prints its token
    ```

=== "pip"

    ```console
    $ django-probe login       # approve access in your browser
    $ django-probe init        # creates a project and prints its token
    ```

`login` authenticates this machine for a single organization you belong to. Pass
`--org <slug>` (found on the organization's page) to skip the picker when setting up
many repositories:

=== "uv"

    ```console
    $ uv run django-probe login --org my-team
    ```

=== "pip"

    ```console
    $ django-probe login --org my-team
    ```

`login` saves its organization credential in your user configuration directory.
`init` uses that credential, names the project after the current directory by default,
and prints a separate project token. Copy that token now, since it is not saved:

=== "uv"

    ```console
    $ uv run django-probe init
    Created project 'my-repo' in My Team.
    Token: 1f2e3d4c5b6a...
    Set this as DJANGO_PROBE_TOKEN wherever you run `django-probe submit`.
    ```

=== "pip"

    ```console
    $ django-probe init
    Created project 'my-repo' in My Team.
    Token: 1f2e3d4c5b6a...
    Set this as DJANGO_PROBE_TOKEN wherever you run `django-probe submit`.
    ```

You can also create an organization and project directly at
[djangoprobe.org](https://djangoprobe.org) and copy the token from the project page.

## Inspect and submit the first scan

=== "uv"

    ```console
    $ export DJANGO_PROBE_TOKEN=<token_from_init>
    $ uv run django-probe scan . # Prints what submit shares
    $ uv run django-probe submit .
    ```

=== "pip"

    ```console
    $ export DJANGO_PROBE_TOKEN=<token_from_init>
    $ django-probe scan . # Prints what submit shares
    $ django-probe submit .
    ```

The `submit` payload will attributed to the project whose token is in
`DJANGO_PROBE_TOKEN`. Export the token however you prefer, as long as `submit`
sees it in its environment. Without it, `submit` sends an anonymous submission.

## Configure payload contents

```toml
[tool.django_probe]
packages = ["django"]  # Default: include statically resolved Django API usage
dependencies = "versions"  # Include dependencies and the versions
django_settings = true  # Share the names of the defined Django settings
```

See [Configuration](configuration.md) for the full set of options.

## Add Django Probe to CI

The job is scheduled rather than added to every pull request because aggregate usage
data does not need frequent or granular reporting.

### GitHub Actions

Add the token as a repository secret named `DJANGO_PROBE_TOKEN` under **Settings →
Secrets and variables → Actions → New repository secret**, then commit this workflow.
`workflow_dispatch` lets you test it immediately from the Actions tab:

=== "uv"

    Call Django Probe's reusable workflow. It checks out the repository, sets up uv,
    and submits from the project's own environment:

    ```yaml
    # .github/workflows/django-probe.yml
    name: Django Probe

    on:
      schedule:
        # Runs monthly. Choose a different minute and hour to help spread load on our servers.
        - cron: "17 4 1 * *"
      workflow_dispatch:

    permissions: {}

    jobs:
      django-probe:
        uses: tim-schilling/django-probe/.github/workflows/django-probe-submit-uv.yml@0.3.2
        with:
          # Path to the Django project to scan, relative to the repository root.
          path: "."
          # Environment to gate the submit job behind. Empty submits without an approval gate.
          environment: ""
          # Space-separated uv dependency groups to sync before scanning.
          dependency-groups: ""
          # Python version for uv to set up. Empty lets uv resolve its own.
          python-version: ""
        secrets:
          DJANGO_PROBE_TOKEN: ${{ secrets.DJANGO_PROBE_TOKEN }}
    ```

    Each option shows its default, so you can remove any you don't need to change.
    To gate submissions behind an approval, see
    [Configuration](configuration.md#github-actions-approval-gate)

    See [Privacy](https://docs.djangoprobe.org/privacy/) for exactly what a payload contains.

=== "pip"

    The reusable workflow is uv-only. Update the project's dependencies yourself,
    then submit:

    ```yaml
    # .github/workflows/django-probe.yml
    name: Django Probe

    on:
      schedule:
        # Runs monthly. Choose a different minute and hour to help spread load on our servers.
        - cron: "17 4 1 * *"
      workflow_dispatch:

    permissions: {}

    jobs:
      submit:
        runs-on: ubuntu-latest
        steps:
          - uses: actions/checkout@v4
            with:
              persist-credentials: false

          - uses: actions/setup-python@v5
            with:
              python-version: "3.x"

          - run: pip install -r requirements.txt

          - run: django-probe submit .
            env:
              DJANGO_PROBE_TOKEN: ${{ secrets.DJANGO_PROBE_TOKEN }}
    ```

### GitLab CI

Add a masked CI/CD variable named `DJANGO_PROBE_TOKEN` under **Settings → CI/CD →
Variables**. GitLab exposes it to the job automatically:

=== "uv"

    ```yaml
    report_probe:
      image: ghcr.io/astral-sh/uv:python3.14-bookworm-slim
      stage: test
      script:
        - uv run django-probe submit .
    ```

=== "pip"

    ```yaml
    report_probe:
      image: python:3.14-slim
      stage: test
      script:
        - pip install -r requirements.txt
        - django-probe submit .
    ```

Schedule the pipeline under **Build → Pipeline schedules**. You can also run the job
once manually to verify the integration.

## CLI reference

| Command | Description |
|---|---|
| `django-probe scan [path]` | Print the payload as JSON without sending anything. |
| `django-probe submit [path] [--server-url] [--dry-run]` | Scan, then send the payload to a server. |
| `django-probe login [--org] [--server-url]` | Authenticate this machine via your browser. |
| `django-probe init [path] [--org] [--name] [--server-url]` | Create a project using your stored login and print its token. |

Every command that reaches a server takes `--server-url`, and refuses a plain-HTTP
one. Loopback addresses are exempt, since a local development
server is not a network hop. To point the CLI at a self-hosted server that has no
TLS, pass `--allow-insecure-http`.

| Env var | Purpose |
|---|---|
| `DJANGO_PROBE_SERVER` | Overrides the default submit target (`https://djangoprobe.org`). |
| `DJANGO_PROBE_TOKEN` | The token from `django-probe init` or a project's page; attributes submissions to it. |
