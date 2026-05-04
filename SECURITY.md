# Security Policy

## Reporting a Vulnerability

Please report security issues privately to **support@creativekonsoles.com** rather than opening a public GitHub issue.

Include a description of the issue, steps to reproduce, and any relevant environment details. We will respond promptly.

## What to Never Commit

- API keys or tokens (`.env` is gitignored — keep it that way)
- Private analytics exports or raw event logs
- Subscriber lists or email addresses
- Cache files containing user preference data

If you discover a committed secret in the repository history, report it immediately so we can rotate the affected key.
