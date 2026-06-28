#!/usr/bin/env python3
"""
============================================================
STEP 9: AUTOMATED TEST SUITE
File: tests/test_all.py

Run: pytest tests/test_all.py -v --tb=short
     python tests/test_all.py  (standalone)
============================================================
"""

import sys
import os
try:
    import tensorflow
    HAS_TENSORFLOW = True
except ImportError:
    HAS_TENSORFLOW = False
import json
import struct
import hashlib
import tempfile
import datetime
import numpy as np
import unittest

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ── Test: IP Protection ──────────────────────────────────────
class TestIPProtection(unittest.TestCase):

    def setUp(self):
        """Create a temp binary STL for testing."""
        self.tmp_stl = tempfile.mktemp(suffix=".stl")
        with open(self.tmp_stl, "wb") as f:
            header = b"Test STL Binary" + b"\x00" * 65
            num_tri = struct.pack("<I", 10)
            f.write(header + num_tri)
            for _ in range(10):
                f.write(struct.pack("<fff", 0.0, 0.0, 1.0))   # normal
                f.write(struct.pack("<fff", 0.0, 0.0, 0.0))   # v1
                f.write(struct.pack("<fff", 1.0, 0.0, 0.0))   # v2
                f.write(struct.pack("<fff", 0.5, 1.0, 0.0))   # v3
                f.write(b"\x00\x00")                           # attr

    def tearDown(self):
        for f in [self.tmp_stl, self.tmp_stl + ".enc",
                  self.tmp_stl + ".dec", self.tmp_stl + ".wm"]:
            try: os.unlink(f)
            except: pass

    def test_encryption_decryption(self):
        """AES-256-GCM encryption/decryption round-trip."""
        from backend.ml.ip_protection import DesignEncryptor
        enc      = DesignEncryptor(key_path=tempfile.mktemp())
        enc_path = self.tmp_stl + ".enc"
        dec_path = self.tmp_stl + ".dec"

        manifest = enc.encrypt_file(self.tmp_stl, enc_path, "TEST_USER")
        self.assertEqual(manifest["owner_id"], "TEST_USER")
        self.assertTrue(os.path.exists(enc_path))

        result = enc.decrypt_file(enc_path, dec_path, "TEST_USER")
        self.assertTrue(result)

        # Verify file content identical after round-trip
        with open(self.tmp_stl, "rb") as f: original = f.read()
        with open(dec_path, "rb") as f: decrypted = f.read()
        self.assertEqual(original, decrypted)

    def test_wrong_owner_blocked(self):
        """Decryption with wrong owner_id should fail."""
        from backend.ml.ip_protection import DesignEncryptor
        enc      = DesignEncryptor(key_path=tempfile.mktemp())
        enc_path = self.tmp_stl + ".enc"
        enc.encrypt_file(self.tmp_stl, enc_path, "OWNER_A")

        with self.assertRaises(PermissionError):
            enc.decrypt_file(enc_path, "/tmp/out.stl", "WRONG_OWNER")

    def test_watermark_embed_detect(self):
        """Watermark should be detectable after embedding."""
        from backend.ml.ip_protection import DesignWatermarker
        wm  = DesignWatermarker()
        out = self.tmp_stl + ".wm"
        wm.embed_stl_watermark(self.tmp_stl, out, "OWNER_001", "DESIGN_A")

        result = wm.detect_watermark(out, "OWNER_001", "DESIGN_A")
        self.assertTrue(result["watermark_detected"])
        self.assertGreater(result["confidence"], 0.8)

    def test_wrong_owner_watermark_fails(self):
        """Watermark detection with wrong owner should fail."""
        from backend.ml.ip_protection import DesignWatermarker
        wm  = DesignWatermarker()
        out = self.tmp_stl + ".wm"
        wm.embed_stl_watermark(self.tmp_stl, out, "OWNER_001", "DESIGN_A")

        result = wm.detect_watermark(out, "WRONG_OWNER", "DESIGN_A")
        self.assertFalse(result["watermark_detected"])

    def test_rsa_sign_verify(self):
        """RSA signing and verification should succeed."""
        from backend.ml.ip_protection import DesignSigner
        key_dir = tempfile.mkdtemp()
        signer  = DesignSigner()
        signer.private_key_path = os.path.join(key_dir, "priv.pem")
        signer.public_key_path  = os.path.join(key_dir, "pub.pem")
        signer.generate_keypair()

        manifest = signer.sign_file(self.tmp_stl, "DESIGNER_TEST")
        self.assertEqual(manifest["designer_id"], "DESIGNER_TEST")

        result = signer.verify_signature(self.tmp_stl)
        self.assertTrue(result["valid"])
        self.assertEqual(result["designer_id"], "DESIGNER_TEST")

    def test_tampered_file_detected(self):
        """Modified file should fail signature verification."""
        from backend.ml.ip_protection import DesignSigner
        key_dir = tempfile.mkdtemp()
        signer  = DesignSigner()
        signer.private_key_path = os.path.join(key_dir, "priv.pem")
        signer.public_key_path  = os.path.join(key_dir, "pub.pem")
        signer.generate_keypair()
        signer.sign_file(self.tmp_stl, "DESIGNER_TEST")

        # Tamper with file
        with open(self.tmp_stl, "ab") as f:
            f.write(b"TAMPERED_DATA")

        result = signer.verify_signature(self.tmp_stl)
        self.assertFalse(result["valid"])
        self.assertEqual(result["reason"], "FILE_TAMPERED")


# ── Test: Blockchain Supply Chain ────────────────────────────
class TestBlockchain(unittest.TestCase):

    def setUp(self):
        from backend.blockchain.fabric_client import LocalLedger, PartAuthenticator
        self.ledger = LocalLedger(":memory:")   # In-memory SQLite
        self.auth   = PartAuthenticator(self.ledger)

        # Create test design file
        self.design_path = tempfile.mktemp(suffix=".stl")
        with open(self.design_path, "wb") as f:
            f.write(b"Test STL" + b"\x00" * 76 + b"\x00\x00\x00\x00")

    def tearDown(self):
        try: os.unlink(self.design_path)
        except: pass

    def test_design_registration(self):
        """Design registration creates blockchain record."""
        result = self.auth.register_design(self.design_path, "DESIGNER_001")
        self.assertIn("design_id", result)
        self.assertTrue(result["design_id"].startswith("DES-"))
        self.assertEqual(len(result["design_hash"]), 64)

    def test_part_registration_and_authentication(self):
        """Full part lifecycle: register → certify → verify."""
        design = self.auth.register_design(self.design_path, "DESIGNER_001")

        params = {"design_hash": design["design_hash"], "nozzle_temp": 200,
                  "layer_height": 0.2, "material": "PLA"}
        part = self.auth.register_part(
            design_id       = design["design_id"],
            manufacturer_id = "MFG_001",
            printer_id      = "PRINTER_001",
            print_params    = params,
            material_batch  = "PLA-BATCH-001"
        )
        self.assertIn("part_id", part)
        self.assertIn("fingerprint", part)

        cert = self.auth.certify_part(part["part_id"], "QA_001", 0.95)
        self.assertIn("cert_id", cert)

        # Authentic verification
        result = self.auth.verify_part_authenticity(
            part["part_id"], part["fingerprint"]
        )
        self.assertTrue(result["authentic"])
        self.assertTrue(result["fingerprint_match"])
        self.assertTrue(result["is_certified"])

    def test_counterfeit_detection(self):
        """Wrong fingerprint → counterfeit."""
        design = self.auth.register_design(self.design_path, "DESIGNER_001")
        part   = self.auth.register_part(design["design_id"], "MFG_001",
                    "PRINTER_001", {}, "BATCH_001")

        result = self.auth.verify_part_authenticity(
            part["part_id"], "FAKE_FINGERPRINT_0000"
        )
        self.assertFalse(result["authentic"])
        self.assertFalse(result["fingerprint_match"])

    def test_chain_integrity(self):
        """Blockchain chain integrity should be valid."""
        result = self.ledger.verify_chain_integrity()
        self.assertTrue(result["is_valid"])
        self.assertEqual(len(result["issues"]), 0)


# ── Test: G-code Security Analyzer ──────────────────────────
class TestGCodeSecurity(unittest.TestCase):

    def _write_gcode(self, content: str) -> str:
        tmp = tempfile.mktemp(suffix=".gcode")
        with open(tmp, "w") as f:
            f.write(content)
        return tmp

    def test_safe_gcode(self):
        from backend.monitoring.anomaly_detector import GCodeSecurityAnalyzer
        gcode = self._write_gcode("; safe print\nG28\nM104 S200\nM140 S60\nG1 X10 Y10 E5 F3000\n")
        try:
            result = GCodeSecurityAnalyzer().analyze_gcode(gcode)
            self.assertLess(result["risk_score"], 0.3)
            self.assertEqual(result["recommendation"], "SAFE_TO_PRINT")
        finally:
            os.unlink(gcode)

    def test_dangerous_temperature(self):
        from backend.monitoring.anomaly_detector import GCodeSecurityAnalyzer
        gcode = self._write_gcode("; dangerous\nM104 S400\n")
        try:
            result = GCodeSecurityAnalyzer().analyze_gcode(gcode)
            self.assertGreater(result["risk_score"], 0.3)
            self.assertTrue(any(a["type"] == "UNSAFE_TEMPERATURE" for a in result["alerts"]))
        finally:
            os.unlink(gcode)

    def test_file_integrity_check(self):
        from backend.monitoring.anomaly_detector import GCodeSecurityAnalyzer
        content = "G28\nM104 S200\n"
        gcode   = self._write_gcode(content)
        try:
            correct_hash = hashlib.sha256(content.encode()).hexdigest()
            wrong_hash   = "0" * 64

            # Correct hash → integrity OK
            result1 = GCodeSecurityAnalyzer().analyze_gcode(gcode, expected_hash=correct_hash)
            self.assertTrue(result1["integrity_ok"])

            # Wrong hash → tampering detected
            result2 = GCodeSecurityAnalyzer().analyze_gcode(gcode, expected_hash=wrong_hash)
            self.assertFalse(result2["integrity_ok"])
        finally:
            os.unlink(gcode)


# ── Test: Statistical Process Control ────────────────────────
class TestSPC(unittest.TestCase):

    def test_normal_process_no_alerts(self):
        from backend.monitoring.anomaly_detector import StatisticalProcessController
        spc    = StatisticalProcessController()
        alerts = []
        for _ in range(40):
            result = spc.update("temp", 200 + np.random.normal(0, 0.3))
            if result:
                alerts.append(result)
        # Expect very few (≤2) alerts for stable process
        self.assertLessEqual(len(alerts), 2)

    def test_drift_detected(self):
        from backend.monitoring.anomaly_detector import StatisticalProcessController
        spc    = StatisticalProcessController()
        alerts = []
        for i in range(40):
            val    = 200 + (i * 0.5 if i > 25 else 0) + np.random.normal(0, 0.1)
            result = spc.update("temp", val)
            if result:
                alerts.extend(result["violations"])
        # Drift should trigger at least one rule
        self.assertGreater(len(alerts), 0)

    def test_process_capability(self):
        from backend.monitoring.anomaly_detector import StatisticalProcessController
        spc = StatisticalProcessController()
        for _ in range(50):
            spc.update("temp", 200 + np.random.normal(0, 0.5))

        cpk = spc.get_process_capability("temp", usl=202, lsl=198)
        self.assertIn("cpk", cpk)
        self.assertIn("rating", cpk)


# ── Test: API Endpoints ──────────────────────────────────────
class TestAPIEndpoints(unittest.TestCase):

    def setUp(self):
        os.environ["JWT_SECRET"] = "test-secret-key"
        from backend.api.app import app
        app.config["TESTING"] = True
        self.client = app.test_client()

    def test_health_endpoint(self):
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertEqual(data["status"], "healthy")

    def test_login_success(self):
        resp = self.client.post("/api/auth/login",
            json={"username": "admin", "password": "Admin@SecurePrint2024!"},
            content_type="application/json")
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertIn("access_token", data)
        self.assertEqual(data["role"], "admin")

    def test_login_wrong_password(self):
        resp = self.client.post("/api/auth/login",
            json={"username": "admin", "password": "WRONG"},
            content_type="application/json")
        self.assertEqual(resp.status_code, 401)

    def test_protected_endpoint_without_token(self):
        resp = self.client.get("/api/dashboard/stats")
        self.assertEqual(resp.status_code, 401)

    def test_dashboard_with_token(self):
        login = self.client.post("/api/auth/login",
            json={"username": "admin", "password": "Admin@SecurePrint2024!"},
            content_type="application/json")
        token = json.loads(login.data)["access_token"]

        resp = self.client.get("/api/dashboard/stats",
                               headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertIn("quality_control", data)
        self.assertIn("supply_chain", data)
        self.assertIn("security", data)

    def test_compliance_report(self):
        login = self.client.post("/api/auth/login",
            json={"username": "admin", "password": "Admin@SecurePrint2024!"},
            content_type="application/json")
        token = json.loads(login.data)["access_token"]

        resp = self.client.get("/api/compliance/report",
                               headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.data)
        self.assertEqual(data["overall_compliance_score"], 100)
        self.assertIn("compliance_checks", data)


# ── Run All Tests ────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("  SecurePrint AI — Full Test Suite")
    print("=" * 60)

    # Run all test suites
    suites = [
        unittest.TestLoader().loadTestsFromTestCase(TestIPProtection),
        unittest.TestLoader().loadTestsFromTestCase(TestBlockchain),
        unittest.TestLoader().loadTestsFromTestCase(TestGCodeSecurity),
        unittest.TestLoader().loadTestsFromTestCase(TestSPC),
        unittest.TestLoader().loadTestsFromTestCase(TestAPIEndpoints),
    ]

    runner = unittest.TextTestRunner(verbosity=2)
    results = [runner.run(suite) for suite in suites]

    total_tests  = sum(r.testsRun for r in results)
    total_errors = sum(len(r.errors) + len(r.failures) for r in results)

    print("\n" + "=" * 60)
    print(f"  TOTAL: {total_tests} tests | FAILED: {total_errors}")
    print(f"  {'✅ ALL TESTS PASSED' if total_errors == 0 else '❌ SOME TESTS FAILED'}")
    print("=" * 60)

    sys.exit(0 if total_errors == 0 else 1)
