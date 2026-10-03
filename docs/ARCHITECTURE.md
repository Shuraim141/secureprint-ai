# Architecture

SecurePrint AI is a three-tier academic MVP for securing the 3D/4D printing lifecycle.

```
React (Vite + Tailwind v4)  --/api-->  FastAPI  -->  SQLAlchemy -> SQLite (prod: PostgreSQL)
  login, 7 modules                       |-- AES-256-GCM encrypted file storage (prod: S3 + KMS)
                                         |-- hash-chained audit log
                                         |-- Ed25519-signed provenance ledger (prod: Hyperledger Fabric)
                                         |-- OpenCV + Random Forest quality models (prod: YOLO/CNN)
                                         |-- simulated printers (prod: OctoPrint/Klipper adapters)
```

## Modules

| Module | Backend | What it does |
|---|---|---|
| Auth + RBAC | `api/auth.py`, `security/rbac.py` | JWT login, Argon2 passwords, lockout, 6 roles, per-endpoint permissions |
| Design security | `api/designs.py`, `geometry/` | Parses STL/OBJ/3MF, SHA-256 + geometric fingerprint, fragile watermark, AES-256-GCM envelope encryption, tamper verdicts, 4D profiles |
| AI quality control | `api/quality.py`, `ml/`, `cv/` | Defect classification from images; process-quality prediction with anomaly detection; metrics stored from real training runs |
| Supply chain | `api/supply_chain.py`, `blockchain/` | Part registry, 9-step workflow, signed hash-chained events, part authentication |
| Manufacturing security | `api/manufacturing.py`, `manufacturing/` | Printer simulator + telemetry, malicious G-code analysis, incidents |
| Audit | `api/audit.py`, `audit/` | Append-only hash-chained log, search, chain verification |
| Compliance | `api/compliance.py`, `services/compliance.py` | 11 automated checks mapped to NIST CSF / ISO 9001, evidence stored per run |

## Key design decisions

* **Integrity everywhere is verifiable, not asserted.** Audit log and provenance are hash chains;
  provenance events are also Ed25519-signed. Verification endpoints recompute from stored data.
* **Honest status.** Compliance checks return UNKNOWN when there is nothing to inspect. ML metrics
  come from real training runs and carry a "synthetic dataset" disclaimer.
* **Adapters for production seams.** `KeyProvider`, `LedgerBackend`, storage and the quality
  model are interfaces so KMS, Fabric, S3 and YOLO can replace the MVP implementations.
* **Single worker.** The audit chain uses a process lock; production would use a database lock.

## Production upgrade path (documented, not deployed)

PostgreSQL, KMS/HSM, S3, Hyperledger Fabric, OctoPrint/Klipper, enterprise IAM (OIDC), httpOnly
cookie sessions, a WAF/reverse proxy with rate limiting, and a validated ML pipeline.
