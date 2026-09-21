# SecurePrint AI

> AI-Powered Security, Quality Assurance, and Intellectual Property Protection for Additive Manufacturing

SecurePrint AI is a comprehensive platform designed to secure the additive manufacturing lifecycle through artificial intelligence, blockchain-based traceability, intellectual property protection, anomaly detection, and compliance automation.

The platform enables manufacturers, researchers, and industrial operators to identify print defects, protect proprietary designs, detect malicious manufacturing activities, verify part authenticity, and maintain regulatory compliance within modern Industry 4.0 environments.

---

## Key Features

### AI-Based Defect Detection

Automatically detect manufacturing defects using machine learning and computer vision.

Supported defect categories include:

* Warping
* Stringing
* Layer shifting
* Under-extrusion
* Nozzle clogging
* General print failures

---

### Intellectual Property Protection

Protect digital manufacturing assets through:

* AES-256-GCM encryption
* RSA digital signatures
* Digital watermarking
* Perceptual hashing
* Ownership verification

---

### Manufacturing Security Monitoring

Detect suspicious and malicious manufacturing behavior by analyzing:

* G-code files
* Printer telemetry
* Process anomalies
* Operational deviations

Security events are categorized by severity and logged for auditing and investigation.

---

### Blockchain-Based Traceability

Create tamper-evident records for manufactured parts through blockchain-inspired ledger technology.

Capabilities include:

* Part registration
* Authenticity verification
* Lifecycle tracking
* Manufacturing fingerprinting
* Audit history preservation

---

### Compliance & Audit Reporting

Generate compliance-ready reports containing:

* Security findings
* Manufacturing events
* Traceability records
* Verification results
* Audit evidence

---

### Real-Time Dashboard

Monitor system activity through a web-based dashboard featuring:

* Security metrics
* Manufacturing insights
* Compliance status
* Quality inspection results
* Operational statistics

---

## System Architecture

```text
┌──────────────────────┐
│  Dashboard Frontend  │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│      Flask API       │
└───────┬─────┬────────┘
        │     │
        │     │
        ▼     ▼
┌──────────┐ ┌──────────────┐
│ AI/ML    │ │ Blockchain   │
│ Services │ │ Ledger       │
└────┬─────┘ └──────┬───────┘
     │              │
     ▼              ▼
┌────────────┐ ┌────────────┐
│ IP Security│ │ Audit Logs │
└────────────┘ └────────────┘
```

---

## Repository Structure

```text
secureprint-ai/
│
├── backend/
│   ├── api/
│   │   └── app.py
│   │
│   ├── ml/
│   │   ├── defect_detector.py
│   │   ├── ip_protection.py
│   │   └── anomaly_detector.py
│   │
│   ├── blockchain/
│   │   └── fabric_client.py
│   │
│   └── monitoring/
│       └── scripts/
│           └── 01_setup_environment.sh
│
├── frontend/
│   └── dashboard.html
│
├── tests/
│   └── test_all.py
│
├── docker/
│   ├── docker-compose.yml
│   └── .gitlab-ci.yml
│
├── Jenkinsfile
├── requirements.txt
└── README.md
```

---

## Technology Stack

### Backend

* Python
* Flask
* JWT Authentication
* SQLite

### Machine Learning

* TensorFlow
* Keras
* Scikit-learn
* OpenCV

### Security

* PyCryptodome
* RSA Cryptography
* AES-256 Encryption

### DevOps

* Docker
* Docker Compose
* Jenkins
* GitLab CI/CD

### Monitoring

* PostgreSQL
* Redis

---

## Installation

### Clone Repository

```bash
git clone https://github.com/Shuraim141/secureprint-ai.git
cd secureprint-ai
```

### Create Virtual Environment

```bash
python -m venv venv
```

Linux/macOS:

```bash
source venv/bin/activate
```

Windows:

```bash
venv\Scripts\activate
```

### Install Dependencies

```bash
pip install -r requirements.txt
```

---

## Quick Start

### Start Backend API

```bash
python backend/api/app.py
```

Default API endpoint:

```text
http://localhost:5000
```

---

### Launch Dashboard

```bash
cd frontend
python -m http.server 8080
```

Dashboard URL:

```text
http://localhost:8080/dashboard.html
```

---

## Docker Deployment

Start all services:

```bash
docker-compose -f docker/docker-compose.yml up -d
```

Stop services:

```bash
docker-compose -f docker/docker-compose.yml down
```

---

## API Overview

### Authentication

```http
POST /api/auth/login
```

Authenticate and obtain JWT token.

---

### Quality Inspection

```http
POST /api/quality/inspect
```

Submit print images for AI-powered inspection.

---

### IP Protection

```http
POST /api/ip/encrypt
POST /api/ip/sign
```

Encrypt and digitally sign design assets.

---

### Supply Chain Verification

```http
POST /api/supply-chain/register-part
POST /api/supply-chain/verify-part
```

Register and verify manufactured parts.

---

### Security Monitoring

```http
POST /api/security/analyze-gcode
GET /api/security/events
```

Analyze manufacturing activity and retrieve security events.

---

### Compliance Reporting

```http
GET /api/compliance/report
```

Generate compliance evidence and audit reports.

---

## Running Tests

Execute the complete test suite:

```bash
pytest tests/test_all.py -v
```

or

```bash
python tests/test_all.py
```

---

## Security Features

* Secure design encryption
* Digital signature verification
* Manufacturing anomaly detection
* G-code threat analysis
* Tamper-evident records
* Audit logging
* JWT authentication
* Compliance reporting

---

## CI/CD

SecurePrint AI supports:

### Jenkins

```text
Jenkinsfile
```

Pipeline includes:

* Security scanning
* Automated testing
* Compliance checks
* Build validation

### GitLab CI/CD

```text
docker/.gitlab-ci.yml
```

Supports:

* Static analysis
* Dependency scanning
* Coverage validation
* Container security scanning

---

## Use Cases

* Aerospace Manufacturing
* Medical Device Production
* Defense Manufacturing
* Industrial Additive Manufacturing
* Research Laboratories
* Digital Supply Chains

---

## Future Enhancements

* Hyperledger Fabric integration
* Real-time printer telemetry streaming
* Multi-tenant deployments
* Kubernetes support
* Advanced AI defect localization
* Digital twin integration

---

## Contributing

Contributions are welcome.

1. Fork the repository
2. Create a feature branch
3. Commit changes
4. Submit a pull request

Please ensure all tests pass before submission.

---

## License

This project is provided for educational, research, and industrial innovation purposes. Review repository licensing terms before commercial deployment.

---

## Acknowledgments

SecurePrint AI combines modern advancements in:

* Artificial Intelligence
* Cybersecurity
* Blockchain Technology
* Additive Manufacturing
* Industry 4.0 Systems

to create a secure and intelligent manufacturing ecosystem.
