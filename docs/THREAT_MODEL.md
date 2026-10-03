# Threat model (STRIDE summary)

| Threat | Asset | Mitigation in this MVP | Residual risk / next step |
|---|---|---|---|
| **Spoofing**: stolen or guessed credentials | Accounts | Argon2 hashes, lockout after repeated failures, short-lived JWT, token revocation on logout, constant-time failed-login path | No MFA; add OIDC + MFA |
| **Tampering**: altered design files | 3D models | SHA-256 + geometric fingerprint + fragile watermark; verdict AUTHENTIC / TAMPERED with metric differences | Watermark is a demonstration, not a robust forensic mark |
| **Tampering**: altered audit or provenance history | Logs, ledger | Hash chains; provenance entries Ed25519-signed; verify endpoints; compliance control fails on tampering (tested) | Local key: an attacker with DB **and** key can rewrite; production uses Fabric/KMS |
| **Tampering**: malicious G-code | Printers | Static analyzer flags unsafe temperatures, out-of-range moves and suspicious commands; HIGH risk raises an incident | Heuristic rules, not a formal verifier |
| **Repudiation** | Actions | Every sensitive action is audited with user, IP, result and severity | Clock and IP trust depend on the reverse proxy |
| **Information disclosure**: design theft | Stored files | AES-256-GCM envelope encryption, ownership checks, RBAC | Master key lives in `.env`; use KMS |
| **Information disclosure**: error leaks | API | Validation errors strip submitted input; strict security headers; no stack traces | Verbose logs must be protected |
| **Denial of service** | API | Upload size caps (early and streaming), bounded query limits | **No request rate limiting** yet; put the API behind a rate-limiting proxy. `/api/compliance/run` is CPU-heavy and should be limited in production |
| **Elevation of privilege** | Roles | Permission checked per endpoint; viewers get 403 on writes (tested) | Roles are a static table |
| **Supply-chain (dependencies)** | Build | CI runs `pip-audit`, `npm audit`, `bandit`, `ruff` on every push | New advisories can fail CI at any time |

## Out of scope
Physical printer security, network segmentation, real defect datasets, and any formal
certification. See the academic disclaimer in the README.
