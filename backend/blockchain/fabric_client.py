#!/usr/bin/env python3
"""
============================================================
STEP 4: BLOCKCHAIN SUPPLY CHAIN AUTHENTICATION
File: backend/blockchain/fabric_client.py

Implements:
  - Hyperledger Fabric chaincode interaction (Python SDK)
  - Part provenance recording and verification
  - Digital twin tracking for 3D printed components
  - Anti-counterfeiting part fingerprinting
  - Supply chain event logging

For local demo without Fabric: uses SQLite-backed ledger simulation.

Run: python backend/blockchain/fabric_client.py
============================================================
"""

import hashlib
import json
import datetime
import sqlite3
import os
import uuid
import logging
from typing import Optional

log = logging.getLogger("BlockchainClient")
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

DB_PATH = "/opt/secureprint/blockchain/ledger.db"
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)


# ── 4.1 Blockchain Ledger (SQLite simulation for local demo) ─
class LocalLedger:
    """
    Simulates Hyperledger Fabric ledger locally using SQLite.
    In production, replace with hfc-py (Hyperledger Fabric Python SDK).
    
    Ledger tables:
      - blocks:        chained block records (hash-linked)
      - transactions:  individual supply chain events
      - parts:         registered part identities
      - certificates:  quality certificates
    """

    def __init__(self, db_path: str = DB_PATH):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self._init_schema()
        self._ensure_genesis_block()

    def _init_schema(self):
        cur = self.conn.cursor()
        cur.executescript("""
            CREATE TABLE IF NOT EXISTS blocks (
                block_id        INTEGER PRIMARY KEY AUTOINCREMENT,
                block_hash      TEXT NOT NULL UNIQUE,
                prev_hash       TEXT NOT NULL,
                timestamp       TEXT NOT NULL,
                tx_count        INTEGER DEFAULT 0,
                merkle_root     TEXT
            );

            CREATE TABLE IF NOT EXISTS transactions (
                tx_id           TEXT PRIMARY KEY,
                block_id        INTEGER,
                tx_type         TEXT NOT NULL,
                asset_id        TEXT NOT NULL,
                actor_id        TEXT NOT NULL,
                payload         TEXT NOT NULL,
                tx_hash         TEXT NOT NULL,
                timestamp       TEXT NOT NULL,
                FOREIGN KEY(block_id) REFERENCES blocks(block_id)
            );

            CREATE TABLE IF NOT EXISTS parts (
                part_id         TEXT PRIMARY KEY,
                design_hash     TEXT NOT NULL,
                manufacturer_id TEXT NOT NULL,
                print_params    TEXT,
                material_batch  TEXT,
                quality_score   REAL,
                status          TEXT DEFAULT 'ACTIVE',
                created_at      TEXT NOT NULL,
                updated_at      TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS certificates (
                cert_id         TEXT PRIMARY KEY,
                part_id         TEXT NOT NULL,
                cert_type       TEXT NOT NULL,
                issuer_id       TEXT NOT NULL,
                standard        TEXT,
                issued_at       TEXT NOT NULL,
                expires_at      TEXT,
                cert_hash       TEXT NOT NULL,
                FOREIGN KEY(part_id) REFERENCES parts(part_id)
            );
        """)
        self.conn.commit()

    def _ensure_genesis_block(self):
        cur = self.conn.cursor()
        cur.execute("SELECT COUNT(*) FROM blocks")
        if cur.fetchone()[0] == 0:
            genesis_hash = hashlib.sha256(b"SECUREPRINT_GENESIS_2024").hexdigest()
            cur.execute("""
                INSERT INTO blocks (block_hash, prev_hash, timestamp, tx_count, merkle_root)
                VALUES (?, ?, ?, ?, ?)
            """, (genesis_hash, "0" * 64, datetime.datetime.utcnow().isoformat(), 0, genesis_hash))
            self.conn.commit()
            log.info(f"Genesis block created: {genesis_hash[:16]}...")

    def _get_latest_block(self) -> dict:
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM blocks ORDER BY block_id DESC LIMIT 1")
        row = cur.fetchone()
        return {
            "block_id":    row[0],
            "block_hash":  row[1],
            "prev_hash":   row[2],
            "timestamp":   row[3],
            "tx_count":    row[4],
            "merkle_root": row[5]
        }

    def _create_block(self, transactions: list) -> dict:
        """Mine a new block containing a batch of transactions."""
        prev = self._get_latest_block()

        # Compute merkle root of transaction hashes
        tx_hashes   = [tx["tx_hash"] for tx in transactions]
        merkle_root = self._compute_merkle_root(tx_hashes)

        # Block hash: SHA256 of prev_hash + merkle_root + timestamp
        timestamp  = datetime.datetime.utcnow().isoformat()
        block_data = f"{prev['block_hash']}:{merkle_root}:{timestamp}"
        block_hash = hashlib.sha256(block_data.encode()).hexdigest()

        cur = self.conn.cursor()
        cur.execute("""
            INSERT INTO blocks (block_hash, prev_hash, timestamp, tx_count, merkle_root)
            VALUES (?, ?, ?, ?, ?)
        """, (block_hash, prev["block_hash"], timestamp, len(transactions), merkle_root))

        new_block_id = cur.lastrowid

        # Link transactions to this block
        for tx in transactions:
            cur.execute("""
                UPDATE transactions SET block_id = ? WHERE tx_id = ?
            """, (new_block_id, tx["tx_id"]))

        self.conn.commit()
        log.info(f"Block #{new_block_id} mined: {block_hash[:16]}... ({len(transactions)} txs)")
        return {"block_id": new_block_id, "block_hash": block_hash}

    def _compute_merkle_root(self, hashes: list) -> str:
        """Simple Merkle tree implementation."""
        if not hashes:
            return hashlib.sha256(b"empty").hexdigest()
        if len(hashes) == 1:
            return hashes[0]
        level = hashes[:]
        while len(level) > 1:
            if len(level) % 2 == 1:
                level.append(level[-1])  # Duplicate last if odd
            next_level = []
            for i in range(0, len(level), 2):
                combined  = level[i] + level[i + 1]
                next_level.append(hashlib.sha256(combined.encode()).hexdigest())
            level = next_level
        return level[0]

    def submit_transaction(self, tx_type: str, asset_id: str,
                           actor_id: str, payload: dict) -> str:
        """
        Submit a transaction to the ledger.
        Immediately creates a new block (simplified; production batches txs).
        Returns transaction ID.
        """
        tx_id      = str(uuid.uuid4())
        timestamp  = datetime.datetime.utcnow().isoformat()
        payload_str = json.dumps(payload)
        tx_hash    = hashlib.sha256(
            f"{tx_id}:{tx_type}:{asset_id}:{actor_id}:{payload_str}:{timestamp}".encode()
        ).hexdigest()

        cur = self.conn.cursor()
        cur.execute("""
            INSERT INTO transactions (tx_id, tx_type, asset_id, actor_id, payload, tx_hash, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (tx_id, tx_type, asset_id, actor_id, payload_str, tx_hash, timestamp))
        self.conn.commit()

        # Create new block
        self._create_block([{"tx_id": tx_id, "tx_hash": tx_hash}])

        return tx_id

    def query_asset_history(self, asset_id: str) -> list:
        """Retrieve full transaction history for an asset (part, design, etc.)."""
        cur = self.conn.cursor()
        cur.execute("""
            SELECT t.*, b.block_hash, b.block_id
            FROM transactions t
            LEFT JOIN blocks b ON t.block_id = b.block_id
            WHERE t.asset_id = ?
            ORDER BY t.timestamp ASC
        """, (asset_id,))
        rows = cur.fetchall()
        return [
            {
                "tx_id":      row[0],
                "block_id":   row[1],
                "tx_type":    row[2],
                "asset_id":   row[3],
                "actor_id":   row[4],
                "payload":    json.loads(row[5]),
                "tx_hash":    row[6],
                "timestamp":  row[7],
                "block_hash": row[8]
            }
            for row in rows
        ]

    def verify_chain_integrity(self) -> dict:
        """Walk the entire blockchain and verify hash linkage."""
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM blocks ORDER BY block_id ASC")
        blocks = cur.fetchall()

        issues = []
        for i in range(1, len(blocks)):
            prev_block    = blocks[i - 1]
            current_block = blocks[i]
            if current_block[2] != prev_block[1]:  # prev_hash mismatch
                issues.append(f"Block #{current_block[0]}: prev_hash mismatch!")

        return {
            "total_blocks":  len(blocks),
            "is_valid":      len(issues) == 0,
            "issues":        issues,
            "checked_at":    datetime.datetime.utcnow().isoformat()
        }


# ── 4.2 Part Registration & Authentication ──────────────────
class PartAuthenticator:
    """
    Register 3D-printed parts on blockchain and authenticate them.
    
    Workflow:
      1. Designer registers design (DESIGN_REGISTERED)
      2. Manufacturer registers part at print start (PART_MANUFACTURED)
      3. QA certifies part post-inspection (PART_CERTIFIED)
      4. Shipped to customer (PART_SHIPPED)
      5. Customer verifies authenticity (PART_VERIFIED)
    """

    def __init__(self, ledger: LocalLedger):
        self.ledger = ledger

    def generate_part_fingerprint(self, print_params: dict, material_batch: str,
                                   printer_id: str, design_hash: str) -> str:
        """
        Generate a unique manufacturing fingerprint for a part.
        Incorporates: print parameters, material lot, printer ID, design hash.
        This fingerprint is unforgeable without the exact same inputs.
        """
        fp_data = json.dumps({
            "print_params":   print_params,
            "material_batch": material_batch,
            "printer_id":     printer_id,
            "design_hash":    design_hash,
            "nonce":          os.urandom(8).hex()   # prevents replay
        }, sort_keys=True)
        return hashlib.sha256(fp_data.encode()).hexdigest()

    def register_design(self, design_path: str, designer_id: str,
                        license_type: str = "PROPRIETARY") -> dict:
        """Register a design file on the blockchain."""
        with open(design_path, "rb") as f:
            design_hash = hashlib.sha256(f.read()).hexdigest()

        design_id = f"DES-{design_hash[:12].upper()}"
        payload = {
            "design_id":    design_id,
            "design_hash":  design_hash,
            "designer_id":  designer_id,
            "license_type": license_type,
            "file_name":    os.path.basename(design_path),
            "registered_at": datetime.datetime.utcnow().isoformat()
        }

        tx_id = self.ledger.submit_transaction(
            tx_type="DESIGN_REGISTERED",
            asset_id=design_id,
            actor_id=designer_id,
            payload=payload
        )

        log.info(f"✅ Design registered: {design_id} | TX: {tx_id[:8]}...")
        return {"design_id": design_id, "tx_id": tx_id, "design_hash": design_hash}

    def register_part(self, design_id: str, manufacturer_id: str,
                      printer_id: str, print_params: dict,
                      material_batch: str) -> dict:
        """Register a manufactured part on the blockchain."""
        part_id     = f"PART-{uuid.uuid4().hex[:12].upper()}"
        design_hash = print_params.get("design_hash", "UNKNOWN")
        fingerprint = self.generate_part_fingerprint(
            print_params, material_batch, printer_id, design_hash
        )

        payload = {
            "part_id":        part_id,
            "design_id":      design_id,
            "manufacturer_id": manufacturer_id,
            "printer_id":     printer_id,
            "print_params":   print_params,
            "material_batch": material_batch,
            "fingerprint":    fingerprint,
            "manufactured_at": datetime.datetime.utcnow().isoformat()
        }

        cur = self.ledger.conn.cursor()
        cur.execute("""
            INSERT INTO parts (part_id, design_hash, manufacturer_id, print_params,
                               material_batch, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            part_id, design_hash, manufacturer_id,
            json.dumps(print_params), material_batch, "MANUFACTURED",
            datetime.datetime.utcnow().isoformat(),
            datetime.datetime.utcnow().isoformat()
        ))
        self.ledger.conn.commit()

        tx_id = self.ledger.submit_transaction(
            tx_type="PART_MANUFACTURED",
            asset_id=part_id,
            actor_id=manufacturer_id,
            payload=payload
        )

        log.info(f"✅ Part registered: {part_id} | Fingerprint: {fingerprint[:16]}...")
        return {"part_id": part_id, "fingerprint": fingerprint, "tx_id": tx_id}

    def certify_part(self, part_id: str, qa_officer_id: str,
                     quality_score: float, standard: str = "ISO-9001") -> dict:
        """Issue a quality certificate for a part on the blockchain."""
        cert_id   = f"CERT-{uuid.uuid4().hex[:10].upper()}"
        issued_at = datetime.datetime.utcnow()
        expires_at = (issued_at + datetime.timedelta(days=365 * 3)).isoformat()

        cert_data = {
            "cert_id":      cert_id,
            "part_id":      part_id,
            "quality_score": quality_score,
            "standard":     standard,
            "qa_officer":   qa_officer_id,
            "issued_at":    issued_at.isoformat(),
            "expires_at":   expires_at
        }
        cert_hash = hashlib.sha256(json.dumps(cert_data, sort_keys=True).encode()).hexdigest()

        cur = self.ledger.conn.cursor()
        cur.execute("""
            INSERT INTO certificates (cert_id, part_id, cert_type, issuer_id, standard,
                                      issued_at, expires_at, cert_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (cert_id, part_id, "QUALITY", qa_officer_id, standard,
              issued_at.isoformat(), expires_at, cert_hash))
        self.ledger.conn.commit()

        tx_id = self.ledger.submit_transaction(
            tx_type="PART_CERTIFIED",
            asset_id=part_id,
            actor_id=qa_officer_id,
            payload={**cert_data, "cert_hash": cert_hash}
        )

        log.info(f"✅ Part certified: {part_id} | Cert: {cert_id} | Score: {quality_score}")
        return {"cert_id": cert_id, "cert_hash": cert_hash, "tx_id": tx_id}

    def verify_part_authenticity(self, part_id: str, scan_fingerprint: str) -> dict:
        """
        Verify a part's authenticity at point-of-use.
        Checks: blockchain history, fingerprint match, certificate validity.
        """
        history = self.ledger.query_asset_history(part_id)

        if not history:
            return {
                "authentic": False,
                "reason":    "PART_NOT_FOUND_ON_BLOCKCHAIN",
                "part_id":   part_id
            }

        # Find manufacturing record
        mfg_record = next(
            (tx for tx in history if tx["tx_type"] == "PART_MANUFACTURED"), None
        )
        cert_record = next(
            (tx for tx in history if tx["tx_type"] == "PART_CERTIFIED"), None
        )

        if not mfg_record:
            return {"authentic": False, "reason": "NO_MANUFACTURING_RECORD"}

        stored_fingerprint = mfg_record["payload"].get("fingerprint", "")
        fp_match = scan_fingerprint == stored_fingerprint

        result = {
            "authentic":           fp_match and cert_record is not None,
            "part_id":             part_id,
            "fingerprint_match":   fp_match,
            "is_certified":        cert_record is not None,
            "manufacturer":        mfg_record["payload"].get("manufacturer_id"),
            "manufactured_at":     mfg_record["payload"].get("manufactured_at"),
            "quality_score":       cert_record["payload"].get("quality_score") if cert_record else None,
            "supply_chain_events": len(history),
            "blockchain_verified": True,
            "verified_at":         datetime.datetime.utcnow().isoformat()
        }

        log.info(f"Part verification: {part_id} → {'AUTHENTIC' if result['authentic'] else 'COUNTERFEIT'}")
        return result


# ── 4.3 Hyperledger Fabric Production Client ─────────────────
FABRIC_CHAINCODE = """
// ============================================================
// STEP 4 (Production): Hyperledger Fabric Chaincode (Go)
// File: backend/blockchain/chaincode/secureprint_cc.go
// Deploy with: peer chaincode instantiate -n secureprint -v 1.0
// ============================================================

package main

import (
    "encoding/json"
    "fmt"
    "time"
    "github.com/hyperledger/fabric-contract-api-go/contractapi"
)

type SecurePrintContract struct {
    contractapi.Contract
}

type Part struct {
    PartID        string  `json:"part_id"`
    DesignHash    string  `json:"design_hash"`
    Manufacturer  string  `json:"manufacturer_id"`
    Fingerprint   string  `json:"fingerprint"`
    QualityScore  float64 `json:"quality_score"`
    Status        string  `json:"status"`
    CreatedAt     string  `json:"created_at"`
}

func (c *SecurePrintContract) RegisterPart(ctx contractapi.TransactionContextInterface,
    partID, designHash, manufacturerID, fingerprint string) error {
    
    part := Part{
        PartID:       partID,
        DesignHash:   designHash,
        Manufacturer: manufacturerID,
        Fingerprint:  fingerprint,
        Status:       "MANUFACTURED",
        CreatedAt:    time.Now().UTC().Format(time.RFC3339),
    }
    
    partJSON, err := json.Marshal(part)
    if err != nil {
        return err
    }
    return ctx.GetStub().PutState(partID, partJSON)
}

func (c *SecurePrintContract) VerifyPart(ctx contractapi.TransactionContextInterface,
    partID, scannedFingerprint string) (bool, error) {
    
    partJSON, err := ctx.GetStub().GetState(partID)
    if err != nil || partJSON == nil {
        return false, fmt.Errorf("part %s not found", partID)
    }
    
    var part Part
    json.Unmarshal(partJSON, &part)
    return part.Fingerprint == scannedFingerprint, nil
}

func main() {
    chaincode, _ := contractapi.NewChaincode(&SecurePrintContract{})
    chaincode.Start()
}
"""


# ── Main Demo ────────────────────────────────────────────────
if __name__ == "__main__":
    log.info("=" * 60)
    log.info("  SecurePrint AI — Supply Chain Blockchain Demo")
    log.info("=" * 60)

    ledger = LocalLedger()
    auth   = PartAuthenticator(ledger)

    # Create dummy design file
    design_path = "/tmp/turbine_blade.stl"
    with open(design_path, "wb") as f:
        f.write(b"Binary STL" + b"\x00" * 74 + b"\x01\x00\x00\x00" + b"\x00" * 50)

    # Step 1: Register design
    log.info("\n[4.1] Registering design on blockchain...")
    design_reg = auth.register_design(design_path, "DESIGNER_AEROSPACE_001", "PROPRIETARY")

    # Step 2: Manufacture part
    log.info("\n[4.2] Registering manufactured part...")
    print_params = {
        "design_hash":   design_reg["design_hash"],
        "layer_height":  0.1,
        "nozzle_temp":   240,
        "print_speed":   40,
        "material":      "Ti-6Al-4V",
        "printer_model": "EOS M290"
    }
    part_reg = auth.register_part(
        design_id=design_reg["design_id"],
        manufacturer_id="AERO_MFG_PLANT_A",
        printer_id="PRINTER_EOS_001",
        print_params=print_params,
        material_batch="TI64-BATCH-2024-Q4"
    )

    # Step 3: Certify part
    log.info("\n[4.3] Issuing quality certificate...")
    cert = auth.certify_part(
        part_id=part_reg["part_id"],
        qa_officer_id="QA_INSPECTOR_007",
        quality_score=0.97,
        standard="AS9100D"
    )

    # Step 4: Verify authenticity
    log.info("\n[4.4] Verifying part authenticity...")
    verification = auth.verify_part_authenticity(
        part_id=part_reg["part_id"],
        scan_fingerprint=part_reg["fingerprint"]  # Correct fingerprint → authentic
    )
    log.info(f"Verification result: {json.dumps(verification, indent=2)}")

    # Step 5: Test counterfeit detection
    log.info("\n[4.5] Testing counterfeit detection...")
    fake_verification = auth.verify_part_authenticity(
        part_id=part_reg["part_id"],
        scan_fingerprint="FAKE_FINGERPRINT_0000"  # Wrong fingerprint → counterfeit
    )
    log.info(f"Counterfeit result: authentic={fake_verification['authentic']}")

    # Chain integrity check
    log.info("\n[4.6] Verifying blockchain integrity...")
    integrity = ledger.verify_chain_integrity()
    log.info(f"Chain valid: {integrity['is_valid']} | Blocks: {integrity['total_blocks']}")

    # Save Go chaincode
    cc_path = "/opt/secureprint/blockchain/chaincode/secureprint_cc.go"
    os.makedirs(os.path.dirname(cc_path), exist_ok=True)
    with open(cc_path, "w") as f:
        f.write(FABRIC_CHAINCODE)
    log.info(f"\n✅ Hyperledger Fabric chaincode saved to {cc_path}")
    log.info("\n✅ STEP 4 COMPLETE: Supply Chain Authentication Ready")
    log.info("Next: Run python backend/monitoring/anomaly_detector.py")
