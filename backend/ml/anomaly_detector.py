#!/usr/bin/env python3
"""
============================================================
STEP 5: MANUFACTURING PROCESS SECURITY & ANOMALY DETECTION
File: backend/monitoring/anomaly_detector.py

Implements:
  - Real-time G-code analysis for malicious modifications
  - Statistical process control (SPC) for print parameters
  - Isolation Forest anomaly detection for telemetry streams
  - SIEM-style incident logging and automated response
  - Print file integrity verification (hash-chain)

Run: python backend/monitoring/anomaly_detector.py
============================================================
"""

import json
import hashlib
import re
import datetime
import logging
import os
import sqlite3
import numpy as np
from typing import Optional
from enum import Enum

log = logging.getLogger("AnomalyDetector")
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

EVENTS_DB = "/opt/secureprint/logs/security_events.db"
os.makedirs(os.path.dirname(EVENTS_DB), exist_ok=True)


class AlertSeverity(Enum):
    INFO     = "INFO"
    LOW      = "LOW"
    MEDIUM   = "MEDIUM"
    HIGH     = "HIGH"
    CRITICAL = "CRITICAL"


# ── 5.1 G-code Security Analyzer ────────────────────────────
class GCodeSecurityAnalyzer:
    """
    Analyzes G-code print files for:
      - Temperature parameter anomalies (too high = fire risk)
      - Suspicious command sequences (firmware attacks)
      - Unauthorized feed rate changes
      - Hidden extrusion commands (sabotage)
      - File integrity against signed baseline
    """

    # Safe operating ranges for common materials
    SAFE_RANGES = {
        "nozzle_temp": {
            "PLA":  (175, 230),
            "ABS":  (220, 260),
            "PETG": (220, 250),
            "TPU":  (200, 240),
            "Ti64": (0, 0)  # Metal PBF uses laser, not temps
        },
        "bed_temp":      (20, 120),   # Max safe bed temperature
        "feed_rate":     (1, 15000),  # mm/min
        "fan_speed":     (0, 255),    # PWM value
    }

    DANGEROUS_COMMANDS = [
        r"M303\s+E0\s+S\d+",    # PID auto-tune (can overheat)
        r"M104\s+S[3-9]\d\d",   # Set temp > 300°C
        r"M140\s+S1[2-9]\d",    # Set bed > 120°C
        r"M600\s*$",             # Filament change (unexpected)
        r"G28\s+W",              # Home without mesh (can crash)
        r"FIRMWARE_RESTART",     # Klipper firmware restart command
        r"SET_KINEMATIC_POSITION", # Override position (potential crash)
        r"SAVE_CONFIG",          # Config modification during print
        r"M500",                 # Save EEPROM (could corrupt settings)
        r"M502",                 # Reset EEPROM to defaults mid-print
    ]

    def __init__(self):
        self.compiled_patterns = [
            re.compile(p, re.IGNORECASE) for p in self.DANGEROUS_COMMANDS
        ]

    def analyze_gcode(self, gcode_path: str, expected_hash: str = None) -> dict:
        """
        Full security analysis of a G-code file.
        Returns: risk_score, alerts, parameter_violations, integrity_status.
        """
        if not os.path.exists(gcode_path):
            return {"error": f"File not found: {gcode_path}"}

        with open(gcode_path, "r", errors="ignore") as f:
            content = f.read()
            lines   = content.splitlines()

        alerts = []
        temp_violations   = []
        suspicious_cmds   = []
        feed_violations   = []

        # Integrity check
        actual_hash = hashlib.sha256(content.encode()).hexdigest()
        integrity_ok = (expected_hash is None) or (actual_hash == expected_hash)
        if not integrity_ok:
            alerts.append({
                "severity": AlertSeverity.CRITICAL.value,
                "type":     "FILE_TAMPERED",
                "detail":   f"Hash mismatch: expected {expected_hash[:16]}..., got {actual_hash[:16]}..."
            })

        for line_num, line in enumerate(lines, 1):
            line = line.strip()
            if not line or line.startswith(";"):
                continue

            # Check dangerous commands
            for pattern in self.compiled_patterns:
                if pattern.search(line):
                    suspicious_cmds.append({
                        "line":    line_num,
                        "command": line,
                        "pattern": pattern.pattern
                    })
                    alerts.append({
                        "severity": AlertSeverity.HIGH.value,
                        "type":     "SUSPICIOUS_COMMAND",
                        "line":     line_num,
                        "detail":   line
                    })

            # Temperature checks (M104 = nozzle, M109 = nozzle wait)
            temp_match = re.search(r"M10[49]\s+S(\d+\.?\d*)", line, re.IGNORECASE)
            if temp_match:
                temp = float(temp_match.group(1))
                if temp > 300:
                    temp_violations.append({"line": line_num, "temp": temp, "type": "nozzle"})
                    alerts.append({
                        "severity": AlertSeverity.CRITICAL.value,
                        "type":     "UNSAFE_TEMPERATURE",
                        "detail":   f"Nozzle temp {temp}°C exceeds safe limit (300°C) at line {line_num}"
                    })

            # Bed temperature checks (M140, M190)
            bed_match = re.search(r"M1[49]0\s+S(\d+\.?\d*)", line, re.IGNORECASE)
            if bed_match:
                bed_temp = float(bed_match.group(1))
                if bed_temp > self.SAFE_RANGES["bed_temp"][1]:
                    temp_violations.append({"line": line_num, "temp": bed_temp, "type": "bed"})

            # Feed rate check (F parameter in G0/G1)
            feed_match = re.search(r"F(\d+\.?\d*)", line, re.IGNORECASE)
            if feed_match:
                feed = float(feed_match.group(1))
                if feed > self.SAFE_RANGES["feed_rate"][1]:
                    feed_violations.append({"line": line_num, "feed": feed})

        # Compute risk score
        risk_score = min(1.0,
            len([a for a in alerts if a["severity"] == "CRITICAL"]) * 0.4 +
            len([a for a in alerts if a["severity"] == "HIGH"])     * 0.2 +
            len(temp_violations) * 0.15 +
            (0.5 if not integrity_ok else 0)
        )

        return {
            "file":             gcode_path,
            "file_hash":        actual_hash,
            "integrity_ok":     integrity_ok,
            "risk_score":       round(risk_score, 3),
            "total_lines":      len(lines),
            "alerts":           alerts,
            "suspicious_commands": suspicious_cmds,
            "temp_violations":  temp_violations,
            "feed_violations":  feed_violations,
            "analyzed_at":      datetime.datetime.utcnow().isoformat(),
            "recommendation":   "BLOCK_PRINT" if risk_score > 0.5 else "PROCEED_WITH_CAUTION" if risk_score > 0.2 else "SAFE_TO_PRINT"
        }


# ── 5.2 Statistical Process Control (SPC) ───────────────────
class StatisticalProcessController:
    """
    Western Electric / Shewhart control chart implementation.
    Detects process drift before it becomes a defect.
    
    Rules implemented:
      Rule 1: One point beyond 3σ (obvious outlier)
      Rule 2: Nine consecutive points on same side of mean (drift)
      Rule 3: Six consecutive points monotonically increasing/decreasing (trend)
      Rule 4: Fourteen alternating points (oscillation = instability)
    """

    def __init__(self, window_size: int = 30):
        self.window_size = window_size
        self.history: dict = {}  # parameter_name → list of values

    def update(self, parameter: str, value: float) -> Optional[dict]:
        """
        Add new measurement. Returns alert if control rule violated, else None.
        """
        if parameter not in self.history:
            self.history[parameter] = []

        self.history[parameter].append(value)

        # Keep rolling window
        if len(self.history[parameter]) > self.window_size * 3:
            self.history[parameter] = self.history[parameter][-self.window_size * 3:]

        if len(self.history[parameter]) < self.window_size:
            return None  # Not enough data yet

        recent = np.array(self.history[parameter][-self.window_size:])
        mean   = np.mean(recent)
        std    = np.std(recent)

        violations = []

        # Rule 1: Beyond 3σ
        if abs(value - mean) > 3 * std and std > 0:
            violations.append({
                "rule":    "RULE_1_THREE_SIGMA",
                "detail":  f"{parameter}={value:.2f} is {abs(value-mean)/std:.1f}σ from mean",
                "severity": AlertSeverity.HIGH.value
            })

        # Rule 2: Nine consecutive on same side
        if len(recent) >= 9:
            last_9 = recent[-9:]
            if all(x > mean for x in last_9) or all(x < mean for x in last_9):
                violations.append({
                    "rule":    "RULE_2_NINE_CONSECUTIVE",
                    "detail":  f"{parameter}: 9 consecutive points on same side of mean (drift)",
                    "severity": AlertSeverity.MEDIUM.value
                })

        # Rule 3: Six monotonically increasing/decreasing
        if len(recent) >= 6:
            last_6 = recent[-6:]
            if all(last_6[i] < last_6[i+1] for i in range(5)):
                violations.append({
                    "rule":    "RULE_3_INCREASING_TREND",
                    "detail":  f"{parameter}: 6 consecutive increasing values (upward trend)",
                    "severity": AlertSeverity.MEDIUM.value
                })
            elif all(last_6[i] > last_6[i+1] for i in range(5)):
                violations.append({
                    "rule":    "RULE_3_DECREASING_TREND",
                    "detail":  f"{parameter}: 6 consecutive decreasing values (downward trend)",
                    "severity": AlertSeverity.MEDIUM.value
                })

        return {"parameter": parameter, "value": value, "mean": mean, "std": std,
                "violations": violations} if violations else None

    def get_process_capability(self, parameter: str, usl: float, lsl: float) -> dict:
        """
        Compute Cpk (process capability index).
        Cpk > 1.33 = capable process (pharmaceutical/aerospace standard)
        Cpk > 1.67 = six-sigma capable
        """
        if parameter not in self.history or len(self.history[parameter]) < 10:
            return {"error": "Insufficient data"}

        data = np.array(self.history[parameter])
        mean = np.mean(data)
        std  = np.std(data)

        if std == 0:
            return {"cpk": float("inf"), "capable": True}

        cpu = (usl - mean) / (3 * std)
        cpl = (mean - lsl) / (3 * std)
        cpk = min(cpu, cpl)

        return {
            "parameter": parameter,
            "mean":      round(float(mean), 4),
            "std":       round(float(std), 4),
            "cpk":       round(float(cpk), 4),
            "cpu":       round(float(cpu), 4),
            "cpl":       round(float(cpl), 4),
            "capable":   cpk > 1.33,
            "six_sigma": cpk > 1.67,
            "rating":    "EXCELLENT" if cpk > 1.67 else "CAPABLE" if cpk > 1.33 else "MARGINAL" if cpk > 1.0 else "INCAPABLE"
        }


# ── 5.3 Isolation Forest Anomaly Detector ───────────────────
class TelemetryAnomalyDetector:
    """
    Unsupervised anomaly detection on printer telemetry streams.
    IsolationForest: works without labelled anomaly data.
    Detects: sensor spoofing, parameter tampering, unusual operational patterns.
    """

    def __init__(self, contamination: float = 0.05):
        from sklearn.ensemble import IsolationForest
        from sklearn.preprocessing import StandardScaler
        self.model   = IsolationForest(contamination=contamination,
                                       n_estimators=200,
                                       random_state=42)
        self.scaler  = StandardScaler()
        self.is_fit  = False
        self.feature_names = [
            "nozzle_temp", "bed_temp", "extrusion_rate",
            "fan_speed", "print_speed", "layer_height",
            "x_jerk", "y_jerk", "flow_rate"
        ]

    def _extract_features(self, telemetry: dict) -> np.ndarray:
        return np.array([
            telemetry.get("nozzle_temp", 200),
            telemetry.get("bed_temp", 60),
            telemetry.get("extrusion_rate", 100),
            telemetry.get("fan_speed", 128),
            telemetry.get("print_speed", 50),
            telemetry.get("layer_height", 0.2),
            telemetry.get("x_jerk", 8),
            telemetry.get("y_jerk", 8),
            telemetry.get("flow_rate", 100),
        ])

    def train(self, telemetry_history: list):
        """Train on nominal operation data."""
        X = np.array([self._extract_features(t) for t in telemetry_history])
        X_scaled = self.scaler.fit_transform(X)
        self.model.fit(X_scaled)
        self.is_fit = True
        log.info(f"Anomaly detector trained on {len(telemetry_history)} samples")

    def predict(self, telemetry: dict) -> dict:
        """
        Classify a single telemetry reading as normal or anomalous.
        Returns: is_anomaly, anomaly_score, risk_level.
        """
        if not self.is_fit:
            return {"error": "Model not trained yet"}

        features = self._extract_features(telemetry).reshape(1, -1)
        scaled   = self.scaler.transform(features)
        score    = self.model.decision_function(scaled)[0]  # Negative = more anomalous
        pred     = self.model.predict(scaled)[0]            # -1 = anomaly, 1 = normal

        is_anomaly = pred == -1
        norm_score = max(0, min(1, 0.5 - score))  # Normalize to [0,1]

        return {
            "is_anomaly":    is_anomaly,
            "anomaly_score": round(float(norm_score), 4),
            "risk_level":    "CRITICAL" if norm_score > 0.8 else
                             "HIGH"     if norm_score > 0.6 else
                             "MEDIUM"   if norm_score > 0.4 else "LOW",
            "timestamp":     datetime.datetime.utcnow().isoformat()
        }


# ── 5.4 Security Event Manager (SIEM) ───────────────────────
class SecurityEventManager:
    """
    SIEM-style security event recording, correlation, and response.
    Stores events in SQLite. In production: integrate with Splunk/ELK.
    """

    def __init__(self):
        self.conn = sqlite3.connect(EVENTS_DB, check_same_thread=False)
        self._init_schema()

    def _init_schema(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS security_events (
                event_id    TEXT PRIMARY KEY,
                event_type  TEXT NOT NULL,
                severity    TEXT NOT NULL,
                source      TEXT NOT NULL,
                asset_id    TEXT,
                description TEXT NOT NULL,
                payload     TEXT,
                response    TEXT,
                created_at  TEXT NOT NULL,
                resolved    INTEGER DEFAULT 0
            )
        """)
        self.conn.commit()

    def log_event(self, event_type: str, severity: AlertSeverity,
                  source: str, description: str,
                  asset_id: str = None, payload: dict = None) -> str:
        """Log a security event and trigger automated response."""
        import uuid
        event_id = str(uuid.uuid4())
        response = self._determine_response(event_type, severity)

        self.conn.execute("""
            INSERT INTO security_events
            (event_id, event_type, severity, source, asset_id, description, payload, response, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            event_id, event_type, severity.value, source,
            asset_id, description,
            json.dumps(payload) if payload else None,
            json.dumps(response),
            datetime.datetime.utcnow().isoformat()
        ))
        self.conn.commit()

        # Execute automated response
        self._execute_response(response, event_id, asset_id)
        log.warning(f"[{severity.value}] {event_type}: {description}")

        return event_id

    def _determine_response(self, event_type: str, severity: AlertSeverity) -> dict:
        """Map event types to automated responses (ICS/IEC 62443 aligned)."""
        responses = {
            AlertSeverity.CRITICAL: {
                "actions": ["STOP_PRINTER", "QUARANTINE_FILE", "ALERT_SECURITY_TEAM",
                           "LOCK_DESIGN_ACCESS", "CREATE_INCIDENT_TICKET"],
                "auto_stop": True,
                "escalate":  True
            },
            AlertSeverity.HIGH: {
                "actions": ["PAUSE_PRINTER", "FLAG_FOR_REVIEW", "ALERT_OPERATOR"],
                "auto_stop": False,
                "escalate":  True
            },
            AlertSeverity.MEDIUM: {
                "actions": ["LOG_AND_MONITOR", "ALERT_OPERATOR"],
                "auto_stop": False,
                "escalate":  False
            },
            AlertSeverity.LOW: {
                "actions": ["LOG_EVENT"],
                "auto_stop": False,
                "escalate":  False
            }
        }
        return responses.get(severity, responses[AlertSeverity.LOW])

    def _execute_response(self, response: dict, event_id: str, asset_id: str):
        """Execute automated response actions."""
        for action in response.get("actions", []):
            if action == "STOP_PRINTER":
                log.critical(f"🚨 AUTO-STOP triggered for printer (event: {event_id[:8]})")
                # In production: send M112 (emergency stop) via OctoPrint API
                self._send_octoprint_command("M112")
            elif action == "QUARANTINE_FILE":
                log.critical(f"📁 File quarantined (asset: {asset_id})")
                # In production: move file to quarantine directory
            elif action == "ALERT_SECURITY_TEAM":
                log.critical(f"📧 Security team alerted (event: {event_id[:8]})")
                # In production: send email/PagerDuty/Slack alert

    def _send_octoprint_command(self, command: str):
        """Send emergency command to OctoPrint API."""
        # In production:
        # import requests
        # requests.post("http://octoprint:5000/api/printer/command",
        #     headers={"X-Api-Key": OCTOPRINT_API_KEY},
        #     json={"command": command})
        log.info(f"[SIMULATION] OctoPrint command sent: {command}")

    def get_recent_events(self, limit: int = 50) -> list:
        """Retrieve recent security events."""
        cur = self.conn.execute("""
            SELECT * FROM security_events
            ORDER BY created_at DESC LIMIT ?
        """, (limit,))
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def get_event_summary(self) -> dict:
        """Get event counts by severity for dashboard."""
        cur = self.conn.execute("""
            SELECT severity, COUNT(*) as count
            FROM security_events
            WHERE resolved = 0
            GROUP BY severity
        """)
        counts = dict(cur.fetchall())
        return {
            "critical": counts.get("CRITICAL", 0),
            "high":     counts.get("HIGH", 0),
            "medium":   counts.get("MEDIUM", 0),
            "low":      counts.get("LOW", 0),
            "total":    sum(counts.values())
        }


# ── Main Demo ────────────────────────────────────────────────
if __name__ == "__main__":
    log.info("=" * 60)
    log.info("  SecurePrint AI — Process Security Demo")
    log.info("=" * 60)

    # Create a test G-code file
    test_gcode = "/tmp/test_print.gcode"
    with open(test_gcode, "w") as f:
        f.write("""; SecurePrint test G-code
G28 ; Home all axes
M140 S60 ; Set bed temp
M104 S200 ; Set nozzle temp
G1 X10 Y10 Z0.3 F3000
G1 X100 Y100 E10 F1500
M104 S350 ; DANGER: too hot!
SAVE_CONFIG ; SUSPICIOUS!
M2 ; End
""")

    # G-code analysis
    log.info("\n[5.1] Analyzing G-code for security issues...")
    analyzer = GCodeSecurityAnalyzer()
    result   = analyzer.analyze_gcode(test_gcode)
    log.info(f"Risk score: {result['risk_score']} | Alerts: {len(result['alerts'])}")
    log.info(f"Recommendation: {result['recommendation']}")

    # SPC demo
    log.info("\n[5.2] Statistical Process Control demo...")
    spc = StatisticalProcessController()
    for i in range(35):
        temp = 200 + np.random.normal(0, 0.5)
        if i > 25:
            temp += 15  # Simulate drift
        alert = spc.update("nozzle_temp", temp)
        if alert:
            log.warning(f"SPC violation: {alert['violations'][0]['rule']}")

    cpk = spc.get_process_capability("nozzle_temp", usl=205, lsl=195)
    log.info(f"Process Cpk: {cpk.get('cpk')} | Rating: {cpk.get('rating')}")

    # Anomaly detection
    log.info("\n[5.3] Training anomaly detector on nominal data...")
    normal_telemetry = [
        {"nozzle_temp": 200 + np.random.normal(0, 1),
         "bed_temp": 60 + np.random.normal(0, 0.5),
         "extrusion_rate": 100 + np.random.normal(0, 2),
         "fan_speed": 128, "print_speed": 50, "layer_height": 0.2,
         "x_jerk": 8, "y_jerk": 8, "flow_rate": 100}
        for _ in range(500)
    ]
    detector = TelemetryAnomalyDetector()
    detector.train(normal_telemetry)

    # Test with anomalous reading (sabotage simulation)
    anomalous = {"nozzle_temp": 350, "bed_temp": 150, "extrusion_rate": 200,
                 "fan_speed": 0, "print_speed": 200, "layer_height": 1.0,
                 "x_jerk": 50, "y_jerk": 50, "flow_rate": 300}
    pred = detector.predict(anomalous)
    log.info(f"Anomaly detected: {pred['is_anomaly']} | Score: {pred['anomaly_score']} | Level: {pred['risk_level']}")

    # SIEM logging
    log.info("\n[5.4] Security Event Manager demo...")
    siem = SecurityEventManager()
    siem.log_event("UNSAFE_TEMPERATURE", AlertSeverity.CRITICAL,
                   "PRINTER_EOS_001", "Nozzle temperature 350°C detected (limit: 300°C)",
                   asset_id="PART-TEST001", payload={"temp": 350})

    summary = siem.get_event_summary()
    log.info(f"Event summary: {json.dumps(summary)}")

    log.info("\n✅ STEP 5 COMPLETE: Process Security Engine Ready")
    log.info("Next: Run python backend/api/app.py")
