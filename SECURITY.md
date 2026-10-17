# Security Policy

## Supported Versions

| Version | Supported |
| :--- | :--- |
| **0.2.x** | :white_check_mark: (Current release) |
| < 0.2.0 | :x: |

## Reporting a Vulnerability

Do **not** disclose suspected vulnerabilities, credentials, or proof-of-concept exploits in public issues or discussions.

Please report security concerns privately through GitHub:
- **Direct Link:** [Open a Private Vulnerability Report](https://github.com/isatyam18/yuntra/security/advisories/new)

When submitting a report, please include:
- A concise description of the issue and potential impact.
- Step-by-step reproduction instructions or a minimal proof of concept.
- Affected Yuntra version, operating system, shell, and Python environment.
- Any logs or redacted CLI output.

We aim to acknowledge reports within 48 hours, validate them privately, prepare a regression-tested patch, and coordinate public disclosure after the release of a fix.

## Security Architecture and Boundaries

### Built-in Guarantees
* **Credential Redaction:** Operates locally to redact common token formats, secret keys, and passwords before logging events or generating adapter handoffs.
* **Plan Gatekeeping:** `yuntra plan review` automatically blocks approval for plans containing likely secrets.
* **Deny-by-Default Policies:** High-risk operations (including `git_push`, auto-commit, network requests, and package installations) are blocked unless explicitly configured in project policies.
* **Safe Recovery:** `yuntra restore` enforces path-traversal safeguards (Zip Slip protection) and rejects overwriting existing directories.

### Limitations
* Yuntra executes local commands explicitly approved by the local user.
* It cannot guarantee interception of operations performed independently by external coding agents.
* Never place production API tokens, private keys, or passwords in project specifications, prompts, handoffs, or verification commands.