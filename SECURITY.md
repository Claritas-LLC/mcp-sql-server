# Security Policy

## Supported Versions

Security fixes are applied to the latest release branch/tag in this repository.

## Reporting a Vulnerability

Please do not disclose vulnerabilities in public issues.

Send details privately to the maintainer with:

- Affected component(s)
- Reproduction steps
- Impact assessment
- Suggested remediation (if available)

If no private channel is configured on GitHub yet, add one in repository settings (Security Advisories) and reference it here.

## Hardening Expectations

- Keep dependencies updated and review advisories.
- Enforce read-only SQL behavior unless explicitly allowed.
- Use least-privilege SQL credentials.
- Keep secrets out of source control.
- Redact sensitive fields in outputs and logs.
- Validate all tool inputs and URI-like values.

## Incident Response

- Triage and confirm impact.
- Contain exposure (credentials rotation, access reduction).
- Patch and release.
- Document root cause and preventive follow-up actions.
