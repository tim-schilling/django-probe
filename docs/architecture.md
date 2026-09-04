# Architecture

This repository builds two separate things from one source tree.

## `django_probe`

This is the Python package that is installed into Django projects and shares aggregate information. Each probe walks the standard library `ast` module's parse tree.

| File | Role |
|---|---|
| `main.py` | CLI entry point. |
| `probes/` | Individual probes. |

## djangoprobe.org

The central Django application that receives submissions, hosted at [djangoprobe.org](https://djangoprobe.org/).

## How a submission flows

1. `django-probe scan` walks the project and runs every registered probe, producing a
   `{key: count}` payload via `payload.py`.
2. `django-probe submit` sends that payload, plus `probe_sources`, to the ingest
   server's `views.py`.
3. `validation.py` checks shape, and the raw submission is stored as-is. See
   [Third-party probe packages](third-party-probes.md) for why nothing gets normalized or described at this point.

## How `login` and `init` work

A device-authorization flow. `login` asks the server for a short-lived code and
a verification URL, opens that URL in a browser, and polls until the request is
approved there. Approval issues a credential scoped to one organization, stored
locally. `init` uses that credential to create a project and print its token.

```mermaid
sequenceDiagram
    participant CLI as django-probe CLI
    participant Server as djangoprobe.org
    participant Browser as User's browser

    CLI->>Server: POST /api/cli/auth/ {org_slug?, label}
    Server-->>CLI: {code, verify_url, expires_in}
    CLI->>Browser: open verify_url (and print it)

    loop until approved, denied, or expired
        CLI->>Server: GET /api/cli/auth/{code}/poll/
        Server-->>CLI: {status: pending}
    end

    Browser->>Server: GET /cli-auth/{code}/ (signs in if needed)
    Server-->>Browser: confirm org, or pick from owned orgs
    Browser->>Server: POST /cli-auth/{code}/ action=approve
    Note over Server: the credential is now tied to<br/>this user and organization

    CLI->>Server: GET /api/cli/auth/{code}/poll/
    Server-->>CLI: {status: approved, token, organization}
    Note over CLI: token saved to ~/.django-probe/credentials.json

    CLI->>Server: POST /api/cli/projects/ (Authorization: CliToken ...)
    Server-->>CLI: {name, token, organization}
    Note over CLI: project token printed for DJANGO_PROBE_TOKEN
```
