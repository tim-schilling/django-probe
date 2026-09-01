# Security Policy

## Reporting a Vulnerability

Report vulnerabilities privately through GitHub: open this repository's **Security**
tab and use **Report a vulnerability**. Do not open a public issue for anything that
could be exploited before a fix ships.

This covers both halves of the repository: the `django_probe` package that runs inside
someone else's project, and the `src/webapp` ingest server. See
[Privacy](https://docs.djangoprobe.org/privacy/) for what a payload can and can't
contain. A report that a payload leaks more than integers, package names, or version
strings is a security report, not just a bug.
