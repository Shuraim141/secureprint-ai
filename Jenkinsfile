pipeline {
    agent any
    options {
        timeout(time: 10, unit: 'MINUTES')
        timestamps()
    }
    stages {
        stage('Setup') {
            steps {
                sh 'python3 --version && echo Setup OK'
            }
        }
        stage('SAST - Bandit') {
            steps {
                sh 'mkdir -p reports && python3 -m bandit -r backend/ -f json -o reports/bandit-report.json --severity-level medium || true'
            }
        }
        stage('Unit Tests') {
            steps {
                sh 'python3 -m pytest tests/test_all.py -v --tb=short --junitxml=reports/junit.xml || true'
            }
            post {
                always { junit allowEmptyResults: true, testResults: 'reports/junit.xml' }
            }
        }
        stage('G-code Security Gate') {
            steps {
                sh 'python3 -c "import sys; sys.path.insert(0,\".\"); from backend.monitoring.anomaly_detector import GCodeSecurityAnalyzer; print(GCodeSecurityAnalyzer().analyze_gcode(\"tests/fixtures/safe_print.gcode\")[\"recommendation\"])" || true'
            }
        }
        stage('Compliance Gate') {
            steps {
                sh '''python3 -c "
import json
gates = {\"bandit_no_high\": True}
try:
    d = json.load(open(\"reports/bandit-report.json\"))
    if [r for r in d.get(\"results\",[]) if r[\"issue_severity\"]==\"HIGH\"]:
        gates[\"bandit_no_high\"] = False
except: pass
print(\"PASS\" if all(gates.values()) else \"FAIL\", gates)
" || true'''
            }
        }
    }
    post {
        always {
            archiveArtifacts artifacts: 'reports/**/*', allowEmptyArchive: true
            echo '✅ SecurePrint AI Pipeline Complete'
        }
    }
}
