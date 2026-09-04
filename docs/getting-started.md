# Getting started

## Install

Add Django Probe to the development dependencies of the project whose usage you want
to share:

```console
$ uv add --dev django-probe
```

## Create a project token

A project token groups scheduled submissions under your organization. Generate one
from the CLI:

```console
$ uv run django-probe login       # approve access in your browser
$ uv run django-probe init        # creates a project and prints its token
```

`login` authenticates this machine for a single organization. Pass `--org
<slug>` (found on the organization's page) to skip the picker when setting up many
repositories:

```console
$ uv run django-probe login --org my-team
```

`login` saves its organization credential in your user configuration directory.
`init` uses that credential, names the project after the current directory by default,
and prints a separate project token. Copy that token now, since it is not saved:

```console
$ uv run django-probe init
Created project 'my-repo' in My Team.
Token: 1f2e3d4c5b6a...
Set this as DJANGO_PROBE_TOKEN wherever you run `django-probe submit`.
```

You can also create an organization and project directly at
[djangoprobe.org](https://djangoprobe.org) and copy the token from the project page.

### What the token is, and what it isn't

A project token is an **association identifier, not an authorization credential**.
It answers "which project do these counts belong to?" and nothing else.

It grants no access. No endpoint reads data with it: it cannot fetch your
submissions, your organization, your projects or your account. All it does is
attribute a submission that would otherwise be anonymous, and anonymous submission
is still fully supported — so the token adds attribution, not permission.

The worst a leaked token allows is someone attributing submissions to your project
and skewing its numbers. It exposes nothing. Regenerate the token from the project
page if that happens; the old one stops working immediately, and you can update CI
afterwards.

That is why the token belongs in a CI secret rather than a committed
`pyproject.toml` — not because the value is sensitive, but because you would rather
strangers not write to your project's numbers.

The credential `login` stores is a different thing, and is a real secret. It
authenticates *you* and can create projects in your organization. It lives in your
user configuration directory with owner-only permissions, and `django-probe logout`
revokes it server-side and deletes it. Don't put it in CI — CI needs a project
token, which is what `init` prints.

## Add Django Probe to CI

### GitHub Actions

Add the token as a repository secret named `DJANGO_PROBE_TOKEN` under **Settings →
Secrets and variables → Actions → New repository secret**, then commit this workflow:

```yaml
# .github/workflows/django-probe.yml
name: Django Probe

on:
  schedule:
    # Choose a different minute and hour to help spread load on our servers.
    - cron: "17 4 1 * *"
  workflow_dispatch:

jobs:
  submit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: astral-sh/setup-uv@v10

      - run: uv run django-probe submit .
        env:
          DJANGO_PROBE_TOKEN: ${{ secrets.DJANGO_PROBE_TOKEN }}
```

The job is scheduled rather than added to every pull request because aggregate usage
data does not need to block or slow down normal builds. `workflow_dispatch` also lets
you test it immediately from the Actions tab.

### GitLab CI

Add a masked CI/CD variable named `DJANGO_PROBE_TOKEN` under **Settings → CI/CD →
Variables**. GitLab exposes it to the job automatically:

```yaml
report_probe:
  image: ghcr.io/astral-sh/uv:python3.14-bookworm-slim
  stage: test
  script:
    - uv run django-probe submit .
```

Schedule the pipeline under **Build → Pipeline schedules**. You can also run the job
once manually to verify the integration.

## Inspect or submit manually

Run the same scan locally before enabling CI if you want to review the data:

```console
$ uv run django-probe scan .      # prints the payload and sends nothing
$ uv run django-probe submit .    # sends the payload
```

Set `DJANGO_PROBE_TOKEN` first to attribute a manual submission to your project. If it
is unset, `submit` sends an anonymous submission.

## CLI reference

| Command | Description |
|---|---|
| `django-probe scan [path]` | Print the payload as JSON without sending anything. |
| `django-probe submit [path] [--server-url] [--dry-run]` | Scan, then send the payload to a server. |
| `django-probe login [--org] [--server-url]` | Authenticate this machine via your browser. |
| `django-probe init [path] [--org] [--name] [--server-url]` | Create a project using your stored login and print its token. |

Every command that reaches a server takes `--server-url`, and refuses a plain-HTTP
one — each request carries a credential in a header, and HTTP puts it in front of
anyone on the network path. Loopback addresses are exempt, since a local development
server is not a network hop. To point the CLI at a self-hosted server that has no
TLS, pass `--allow-insecure-http`.

| Env var | Purpose |
|---|---|
| `DJANGO_PROBE_SERVER` | Overrides the default submit target (`https://djangoprobe.org`). |
| `DJANGO_PROBE_TOKEN` | The token from `django-probe init` or a project's page; attributes submissions to it. |
