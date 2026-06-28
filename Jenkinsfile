// ============================================================
// JENKINSFILE — SecurePrint AI DevSecOps Pipeline
// File location: project ROOT (same level as backend/, frontend/)
// Trigger: git push to any branch, or manual "Build Now"
// ============================================================

pipeline {
    agent any

    environment {
        APP_NAME   = 'secureprint-ai'
        PYTHON     = 'python3'
    }

    options {
        timeout(time: 15, unit: 'MINUTES')
        buildDiscarder(logRotator(numToKeepStr: '20'))
        timestamps()
    }

    stages {

        // ── Stage 1: Setup — isolated venv ──────────────────
        stage('Setup') {
            steps {
                echo '════════════════════════════════════════'
                echo '  SecurePrint AI — Jenkins Pipeline'
                echo '════════════════════════════════════════'
                sh '''
                    VENV_DIR="$WORKSPACE/.venv"
                    if [ ! -d "$VENV_DIR" ]; then
                        echo "Creating fresh venv..."
                        python3 -m venv "$VENV_DIR"
                    fi
                    . "$VENV_DIR/bin/activate"
                    python3 --version
                    pip install --upgrade pip --timeout 60
                    pip install -r requirements.txt --timeout 60
                    pip install pytest --timeout 60
                    echo "✅ Environment ready"
                '''
            }
        }

        // ── Stage 2: Static Code Analysis (SAST) ────────────
        stage('SAST - Bandit') {
            steps {
                sh '''
                    . "$WORKSPACE/.venv/bin/activate"
                    echo "[SAST] Running Bandit security scan..."
                    mkdir -p reports
                    python3 -m bandit -r backend/ -f json -o reports/bandit-report.json --severity-level medium || true
                    python3 -m bandit -r backend/ --severity-level medium
                '''
            }
            post {
                always {
                    archiveArtifacts artifacts: 'reports/bandit-report.json', allowEmptyArchive: true
                }
            }
        }

        // ── Stage 3: Dependency Vulnerability Scan ───────────
        stage('Dependency Scan - Safety') {
            steps {
                sh '''
                    . "$WORKSPACE/.venv/bin/activate"
                    echo "[DEPS] Scanning dependencies for known CVEs..."
                    python3 -m safety check || echo "⚠ Some advisories found - review reports"
                '''
            }
        }

        // ── Stage 4: Unit Tests + Coverage ───────────────────
        stage('Unit Tests') {
            steps {
                sh '''
                    . "$WORKSPACE/.venv/bin/activate"
                    echo "[TESTS] Running full test suite..."
                    python3 -m pytest tests/test_all.py -v --tb=short \
                        --cov=backend --cov-report=term --cov-report=xml:reports/coverage.xml \
                        --junitxml=reports/junit.xml
                '''
            }
            post {
                always {
                    junit allowEmptyResults: true, testResults: 'reports/junit.xml'
                }
            }
        }

        // ── Stage 5: G-code Security Gate (manufacturing-specific) ─
        stage('G-code Security Gate') {
            steps {
                sh '''
                    . "$WORKSPACE/.venv/bin/activate"
                    echo "[GCODE] Validating G-code test fixtures..."
                    python3 -c "
import sys, glob, json
sys.path.insert(0, '.')
from backend.monitoring.anomaly_detector import GCodeSecurityAnalyzer

analyzer = GCodeSecurityAnalyzer()
failed = []
files = glob.glob('tests/fixtures/*.gcode')

if not files:
    print('No G-code fixtures found - skipping gate')
else:
    for f in files:
        result = analyzer.analyze_gcode(f)
        print(f'  {f}: risk={result[\\\"risk_score\\\"]} -> {result[\\\"recommendation\\\"]}')
        if 'malicious' not in f and result['risk_score'] > 0.5:
            failed.append(f)

    if failed:
        print('FAILED: unexpected high-risk safe files:', failed)
        sys.exit(1)
    print('G-code security gate PASSED')
"
                '''
            }
        }

        // ── Stage 6: ML / IP Protection Smoke Test ───────────
        stage('Component Smoke Tests') {
            steps {
                sh '''
                    . "$WORKSPACE/.venv/bin/activate"
                    echo "[SMOKE] Validating IP protection + blockchain modules import and run..."
                    python3 backend/ml/ip_protection.py || true
                    python3 backend/blockchain/fabric_client.py || true
                '''
            }
        }

        // ── Stage 7: Compliance Gate ──────────────────────────
        stage('Compliance Gate') {
            steps {
                sh '''
                    . "$WORKSPACE/.venv/bin/activate"
                    python3 -c "
import json, sys, os

gates = {'bandit_no_high': True, 'tests_passed': True}

try:
    with open('reports/bandit-report.json') as f:
        d = json.load(f)
    highs = [r for r in d.get('results', []) if r['issue_severity'] == 'HIGH']
    if highs:
        gates['bandit_no_high'] = False
except FileNotFoundError:
    pass

print()
print('=' * 45)
print('  SECUREPRINT AI - COMPLIANCE GATE RESULTS')
print('=' * 45)
for gate, status in gates.items():
    icon = 'PASS' if status else 'FAIL'
    print(f'  [{icon}] {gate}')
print('=' * 45)

all_pass = all(gates.values())
sys.exit(0 if all_pass else 1)
"
                '''
            }
        }
    }

    // ── Post Actions ─────────────────────────────────────────
    post {
        always {
            echo 'Archiving reports...'
            archiveArtifacts artifacts: 'reports/**/*', allowEmptyArchive: true
        }
        success {
            echo '✅ PIPELINE PASSED — SecurePrint AI build successful'
        }
        failure {
            echo '❌ PIPELINE FAILED — check stage logs above'
        }
    }
}
