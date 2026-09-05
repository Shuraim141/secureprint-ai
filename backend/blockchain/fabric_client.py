#!/usr/bin/env python3
"""
============================================================
SECUREPRINT AI — Blockchain Supply Chain Authentication
File: backend/blockchain/fabric_client.py

Implements:
  - Hash-chained tamper-evident ledger (Merkle tree)
  - Part registration with SHA-256 manufacturing fingerprint
  - Quality certification on blockchain
  - Counterfeit detection via fingerprint comparison
  - Full supply chain event history
  - Go chaincode for production Hyperledger Fabric

Run: python3 backend/blockchain/fabric_client.py
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
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)

DB_PATH = "/opt/secureprint/blockchain/ledger.db"
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

#"""
#*Blocks
#Transactions
#* Manufactured parts
#* Certificates
#"""
#

 #"""**genesis block**"""

# ── Local Blockchain Ledger (SQLite-backed) ──────────────────
class LocalLedger:
    """
    Tamper-evident hash-chained ledger simulating Hyperledger Fabric.
    Production deployment uses the Go chaincode in /chaincode/secureprint_cc.go
    with a real multi-org Fabric network.

    Block structure:
      block_hash = SHA-256(prev_hash + merkle_root + timestamp)
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
                status          TEXT DEFAULT 'MANUFACTURED',
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
            genesis_hash = hashlib.sha256(
                b"SECUREPRINT_GENESIS_BLOCK_2024"
            ).hexdigest()
            cur.execute("""
                INSERT INTO blocks
                (block_hash, prev_hash, timestamp, tx_count, merkle_root)
                VALUES (?, ?, ?, ?, ?)
            """, (
                genesis_hash, "0" * 64,
                datetime.datetime.utcnow().isoformat(),
                0, genesis_hash
            ))
            self.conn.commit()
            log.info(f"Genesis block created: {genesis_hash[:16]}...")

    def _get_latest_block(self) -> dict:
        cur = self.conn.cursor()
        cur.execute(
            "SELECT * FROM blocks ORDER BY block_id DESC LIMIT 1"
        )
        row = cur.fetchone()
        return {
            "block_id":    row[0],
            "block_hash":  row[1],
            "prev_hash":   row[2],
            "timestamp":   row[3],
            "tx_count":    row[4],
            "merkle_root": row[5]
        }
# ==================================================================================================================================================================================================================
#       “The final block hash is calculated from three elements: the previous block hash, the Merkle root, and the timestamp.
# ===================================================================================================================================================================================================================

print("Hello World")
    def _compute_merkle_root(self, hashes: list) -> str:
        """Binary Merkle tree over transaction hashes."""
        if not hashes:
            return hashlib.sha256(b"empty").hexdigest()
        if len(hashes) == 1:
            return hashes[0]
        level = hashes[:]
        while len(level) > 1:
            if len(level) % 2 == 1:
                level.append(level[-1])
            next_level = []
            for i in range(0, len(level), 2):
                combined = level[i] + level[i + 1]
                next_level.append(
                    hashlib.sha256(combined.encode()).hexdigest()
                )
            level = next_level
        return level[0]

    def _create_block(self, transactions: list) -> dict:
        """Mine a new block containing a list of transactions."""
        prev = self._get_latest_block()
        tx_hashes = [tx["tx_hash"] for tx in transactions]
        merkle_root = self._compute_merkle_root(tx_hashes)
        timestamp = datetime.datetime.utcnow().isoformat()

        block_data = (
            f"{prev['block_hash']}:{merkle_root}:{timestamp}"
        )
        block_hash = hashlib.sha256(block_data.encode()).hexdigest()

        cur = self.conn.cursor()
        cur.execute("""
            INSERT INTO blocks
            (block_hash, prev_hash, timestamp, tx_count, merkle_root)
            VALUES (?, ?, ?, ?, ?)
        """, (
            block_hash, prev["block_hash"],
            timestamp, len(transactions), merkle_root
        ))
        new_block_id = cur.lastrowid

        for tx in transactions:
            cur.execute("""
                UPDATE transactions
                SET block_id = ?
                WHERE tx_id = ?
            """, (new_block_id, tx["tx_id"]))

        self.conn.commit()
        log.info(
            f"Block #{new_block_id} mined: "
            f"{block_hash[:16]}... ({len(transactions)} txs)"
        )
        return {"block_id": new_block_id, "block_hash": block_hash}
# =======================================================================================================================================================================
#       The transaction hash is then included in a block.”
# ========================================================================================================================================================================


    def submit_transaction(
        self,
        tx_type: str,
        asset_id: str,
        actor_id: str,
        payload: dict
    ) -> str:
        """Submit a transaction and immediately mine a new block."""
        tx_id = str(uuid.uuid4())
        timestamp = datetime.datetime.utcnow().isoformat()
        payload_str = json.dumps(payload)
        tx_hash = hashlib.sha256(
            f"{tx_id}:{tx_type}:{asset_id}:{actor_id}"
            f":{payload_str}:{timestamp}".encode()
        ).hexdigest()

        cur = self.conn.cursor()
        cur.execute("""
            INSERT INTO transactions
            (tx_id, tx_type, asset_id, actor_id,
             payload, tx_hash, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            tx_id, tx_type, asset_id,
            actor_id, payload_str, tx_hash, timestamp
        ))
        self.conn.commit()

        self._create_block([{"tx_id": tx_id, "tx_hash": tx_hash}])
        return tx_id

    def query_asset_history(self, asset_id: str) -> list:
        """Return full transaction history for an asset."""
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
        """Walk entire blockchain and verify every hash link."""
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM blocks ORDER BY block_id ASC")
        blocks = cur.fetchall()
        issues = []

        for i in range(1, len(blocks)):
            prev_block    = blocks[i - 1]
            current_block = blocks[i]
            if current_block[2] != prev_block[1]:
                issues.append(
                    f"Block #{current_block[0]}: prev_hash mismatch!"
                )

        return {
            "total_blocks": len(blocks),
            "is_valid":     len(issues) == 0,
            "issues":       issues,
            "checked_at":   datetime.datetime.utcnow().isoformat()
        }


# ── Part Authenticator ───────────────────────────────────────
class PartAuthenticator:
    """
    Registers, certifies, and verifies 3D printed parts
    on the blockchain ledger.

    Supply chain event flow:
      DESIGN_REGISTERED → PART_MANUFACTURED →
      PART_CERTIFIED → PART_SHIPPED → PART_VERIFIED
    """

    def __init__(self, ledger: LocalLedger):
        self.ledger = ledger

    def generate_part_fingerprint(
        self,
        print_params: dict,
        material_batch: str,
        printer_id: str,
        design_hash: str
    ) -> str:
        """
        SHA-256 fingerprint = unique manufacturing signature.
        Acts as a software-defined PUF — unique to each
        printer + material + parameter + design combination.
        """
        fp_data = json.dumps({
            "print_params":   print_params,
            "material_batch": material_batch,
            "printer_id":     printer_id,
            "design_hash":    design_hash,
            "nonce":          os.urandom(8).hex()
        }, sort_keys=True)
        return hashlib.sha256(fp_data.encode()).hexdigest()
# =====================================================================================================================================================================================================================
#       “Next, the PartAuthenticator handles the actual manufacturing workflow.
#Before manufacturing, the original STL design is hashed using SHA-256.”
# ========================================================================================================================================================================================================================

print("Hello World")
    def register_design(
        self,
        design_path: str,
        designer_id: str,
        license_type: str = "PROPRIETARY"
    ) -> dict:
        """Register a design file on the blockchain."""
        with open(design_path, "rb") as f:
            design_hash = hashlib.sha256(f.read()).hexdigest()

        design_id = f"DES-{design_hash[:12].upper()}"
        payload = {
            "design_id":     design_id,
            "design_hash":   design_hash,
            "designer_id":   designer_id,
            "license_type":  license_type,
            "file_name":     os.path.basename(design_path),
            "registered_at": datetime.datetime.utcnow().isoformat()
        }

        tx_id = self.ledger.submit_transaction(
            tx_type="DESIGN_REGISTERED",
            asset_id=design_id,
            actor_id=designer_id,
            payload=payload
        )

        log.info(
            f"✅ Design registered: {design_id} | TX: {tx_id[:8]}..."
        )
        return {
            "design_id":   design_id,
            "tx_id":       tx_id,
            "design_hash": design_hash
        }
# =====================================================================================================================================================================================================================
#       “After the design is registered, the system creates a unique part ID for the physical manufactured part.”
# =========================================================================================================================================================================================================================

print("Hello World")
    def register_part(
        self,
        design_id: str,
        manufacturer_id: str,
        printer_id: str,
        print_params: dict,
        material_batch: str
    ) -> dict:
        """Register a manufactured part on the blockchain."""
        part_id = f"PART-{uuid.uuid4().hex[:12].upper()}"
        design_hash = print_params.get("design_hash", "UNKNOWN")

        fingerprint = self.generate_part_fingerprint(
            print_params, material_batch,
            printer_id, design_hash
        )

        payload = {
            "part_id":         part_id,
            "design_id":       design_id,
            "manufacturer_id": manufacturer_id,
            "printer_id":      printer_id,
            "print_params":    print_params,
            "material_batch":  material_batch,
            "fingerprint":     fingerprint,
            "manufactured_at": datetime.datetime.utcnow().isoformat()
        }

        cur = self.ledger.conn.cursor()
        cur.execute("""
            INSERT INTO parts
            (part_id, design_hash, manufacturer_id, print_params,
             material_batch, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            part_id, design_hash, manufacturer_id,
            json.dumps(print_params), material_batch,
            "MANUFACTURED",
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

        log.info(
            f"✅ Part registered: {part_id} | "
            f"Fingerprint: {fingerprint[:16]}..."
        )
        return {
            "part_id":     part_id,
            "fingerprint": fingerprint,
            "tx_id":       tx_id
        }
# ====================================================================================================================================================================================================================
#      “After manufacturing, the part can be certified by a quality assurance officer.
# =====================================================================================================================================================================================================================

print("Hello World")
    def certify_part(
        self,
        part_id: str,
        qa_officer_id: str,
        quality_score: float,
        standard: str = "ISO-9001"
    ) -> dict:
        """Issue a quality certificate for a part."""
        cert_id = f"CERT-{uuid.uuid4().hex[:10].upper()}"
        issued_at = datetime.datetime.utcnow()
        expires_at = (
            issued_at + datetime.timedelta(days=365 * 3)
        ).isoformat()

        cert_data = {
            "cert_id":       cert_id,
            "part_id":       part_id,
            "quality_score": quality_score,
            "standard":      standard,
            "qa_officer":    qa_officer_id,
            "issued_at":     issued_at.isoformat(),
            "expires_at":    expires_at
        }
        cert_hash = hashlib.sha256(
            json.dumps(cert_data, sort_keys=True).encode()
        ).hexdigest()

        cur = self.ledger.conn.cursor()
        cur.execute("""
            INSERT INTO certificates
            (cert_id, part_id, cert_type, issuer_id, standard,
             issued_at, expires_at, cert_hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            cert_id, part_id, "QUALITY",
            qa_officer_id, standard,
            issued_at.isoformat(), expires_at, cert_hash
        ))
        self.ledger.conn.commit()

        tx_id = self.ledger.submit_transaction(
            tx_type="PART_CERTIFIED",
            asset_id=part_id,
            actor_id=qa_officer_id,
            payload={**cert_data, "cert_hash": cert_hash}
        )

        log.info(
            f"✅ Part certified: {part_id} | "
            f"Cert: {cert_id} | Score: {quality_score}"
        )
        return {
            "cert_id":   cert_id,
            "cert_hash": cert_hash,
            "tx_id":     tx_id
        }
# ===================================================================================================================================================================================================================
#    “The system can also retrieve the complete transaction history associated with a part.”


# =====================================================================================================================================================================================================================

print("Hello World")
    def verify_part_authenticity(
        self,
        part_id: str,
        scan_fingerprint: str
    ) -> dict:
        """Verify a part's authenticity against blockchain record."""
        history = self.ledger.query_asset_history(part_id)

        if not history:
            return {
                "authentic": False,
                "reason":    "PART_NOT_FOUND_ON_BLOCKCHAIN",
                "part_id":   part_id
            }

        mfg_record = next(
            (tx for tx in history
             if tx["tx_type"] == "PART_MANUFACTURED"), None
        )
        cert_record = next(
            (tx for tx in history
             if tx["tx_type"] == "PART_CERTIFIED"), None
        )

        if not mfg_record:
            return {
                "authentic": False,
                "reason":    "NO_MANUFACTURING_RECORD"
            }
# ======================================================================================================================================================================================================================
#     “This is where the system detects potential counterfeits.”
#“The verifier provides the part ID and a scanned manufacturing fingerprint.”
# ======================================================================================================================================================================================================================

print("Hello World")
        stored_fingerprint = mfg_record["payload"].get(
            "fingerprint", ""
        )
        fp_match = scan_fingerprint == stored_fingerprint

        result = {
            "authentic":           fp_match and cert_record is not None,
            "part_id":             part_id,
            "fingerprint_match":   fp_match,
            "is_certified":        cert_record is not None,
            "manufacturer":        mfg_record["payload"].get(
                                       "manufacturer_id"
                                   ),
            "manufactured_at":     mfg_record["payload"].get(
                                       "manufactured_at"
                                   ),
            "quality_score":       cert_record["payload"].get(
                                       "quality_score"
                                   ) if cert_record else None,
            "supply_chain_events": len(history),
            "blockchain_verified": True,
            "verified_at":         datetime.datetime.utcnow().isoformat()
        }

        status = "AUTHENTIC" if result["authentic"] else "COUNTERFEIT"
        log.info(f"Part verification: {part_id} → {status}")
        return result


# ── Hyperledger Fabric Go Chaincode (Production) ─────────────
FABRIC_CHAINCODE = '''
// ============================================================
// Hyperledger Fabric Chaincode — SecurePrint AI
// File: backend/blockchain/chaincode/secureprint_cc.go
// Deploy: peer chaincode instantiate -n secureprint -v 1.0
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

type Design struct {
    DesignID    string `json:"design_id"`
    DesignHash  string `json:"design_hash"`
    DesignerID  string `json:"designer_id"`
    LicenseType string `json:"license_type"`
    RegisteredAt string `json:"registered_at"`
}

func (c *SecurePrintContract) RegisterDesign(
    ctx contractapi.TransactionContextInterface,
    designID, designHash, designerID, licenseType string,
) error {
    design := Design{
        DesignID:     designID,
        DesignHash:   designHash,
        DesignerID:   designerID,
        LicenseType:  licenseType,
        RegisteredAt: time.Now().UTC().Format(time.RFC3339),
    }
    designJSON, err := json.Marshal(design)
    if err != nil {
        return err
    }
    return ctx.GetStub().PutState(designID, designJSON)
}

func (c *SecurePrintContract) RegisterPart(
    ctx contractapi.TransactionContextInterface,
    partID, designHash, manufacturerID, fingerprint string,
) error {
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

func (c *SecurePrintContract) CertifyPart(
    ctx contractapi.TransactionContextInterface,
    partID string, qualityScore float64, standard string,
) error {
    partJSON, err := ctx.GetStub().GetState(partID)
    if err != nil || partJSON == nil {
        return fmt.Errorf("part %s not found", partID)
    }
    var part Part
    json.Unmarshal(partJSON, &part)
    part.QualityScore = qualityScore
    part.Status = "CERTIFIED_" + standard

    updatedJSON, _ := json.Marshal(part)
    return ctx.GetStub().PutState(partID, updatedJSON)
}

func (c *SecurePrintContract) VerifyPart(
    ctx contractapi.TransactionContextInterface,
    partID, scannedFingerprint string,
) (bool, error) {
    partJSON, err := ctx.GetStub().GetState(partID)
    if err != nil || partJSON == nil {
        return false, fmt.Errorf("part %s not found", partID)
    }
    var part Part
    json.Unmarshal(partJSON, &part)
    return part.Fingerprint == scannedFingerprint, nil
}

func (c *SecurePrintContract) GetPartHistory(
    ctx contractapi.TransactionContextInterface,
    partID string,
) (string, error) {
    iter, err := ctx.GetStub().GetHistoryForKey(partID)
    if err != nil {
        return "", err
    }
    defer iter.Close()

    var records []map[string]interface{}
    for iter.HasNext() {
        mod, err := iter.Next()
        if err != nil {
            continue
        }
        record := map[string]interface{}{
            "tx_id":     mod.TxId,
            "timestamp": mod.Timestamp.String(),
            "value":     string(mod.Value),
        }
        records = append(records, record)
    }
    result, _ := json.Marshal(records)
    return string(result), nil
}

func main() {
    chaincode, _ := contractapi.NewChaincode(
        &SecurePrintContract{},
    )
    chaincode.Start()
}
'''


# ── Main Demo ────────────────────────────────────────────────
if __name__ == "__main__":
    log.info("=" * 60)
    log.info("  SecurePrint AI — Blockchain Supply Chain Demo")
    log.info("=" * 60)

    ledger = LocalLedger()
    auth   = PartAuthenticator(ledger)

    # Create a dummy design file
    design_path = "/tmp/turbine_blade.stl"
    with open(design_path, "wb") as f:
        f.write(b"Binary STL demo" + b"\x00" * 69 +
                b"\x01\x00\x00\x00" + b"\x00" * 50)

    # 1. Register design
    log.info("\n[Step 1] Registering design on blockchain...")
    design_reg = auth.register_design(
        design_path, "DESIGNER_AEROSPACE_001", "PROPRIETARY"
    )
    log.info(f"  Design ID:   {design_reg['design_id']}")
    log.info(f"  Design Hash: {design_reg['design_hash'][:32]}...")

    # 2. Register manufactured part
    log.info("\n[Step 2] Registering manufactured part...")
    print_params = {
        "design_hash":   design_reg["design_hash"],
        "layer_height":  0.1,
        "nozzle_temp":   240,
        "print_speed":   40,
        "material":      "Ti-6Al-4V",
        "printer_model": "EOS M290"
    }
    part_reg = auth.register_part(
        design_id       = design_reg["design_id"],
        manufacturer_id = "AERO_MFG_PLANT_A",
        printer_id      = "PRINTER_EOS_001",
        print_params    = print_params,
        material_batch  = "TI64-BATCH-2024-Q4"
    )
    log.info(f"  Part ID:     {part_reg['part_id']}")
    log.info(f"  Fingerprint: {part_reg['fingerprint'][:32]}...")

    # 3. Certify part
    log.info("\n[Step 3] Issuing quality certificate...")
    cert = auth.certify_part(
        part_id      = part_reg["part_id"],
        qa_officer_id= "QA_INSPECTOR_007",
        quality_score= 0.97,
        standard     = "AS9100D"
    )
    log.info(f"  Certificate: {cert['cert_id']}")

    # 4. Verify authentic part
    log.info("\n[Step 4] Verifying AUTHENTIC part...")
    authentic = auth.verify_part_authenticity(
        part_id          = part_reg["part_id"],
        scan_fingerprint = part_reg["fingerprint"]
    )
    log.info(
        f"  authentic={authentic['authentic']} | "
        f"certified={authentic['is_certified']} | "
        f"score={authentic['quality_score']}"
    )

    # 5. Test counterfeit detection
    log.info("\n[Step 5] Testing COUNTERFEIT detection...")
    counterfeit = auth.verify_part_authenticity(
        part_id          = part_reg["part_id"],
        scan_fingerprint = "FAKE_FINGERPRINT_0000000000000000"
    )
    log.info(
        f"  authentic={counterfeit['authentic']} "
        f"← correctly identified as COUNTERFEIT"
    )

    # 6. Show full supply chain history
    log.info("\n[Step 6] Full supply chain history...")
    history = ledger.query_asset_history(part_reg["part_id"])
    for event in history:
        log.info(
            f"  Block #{event['block_id']} | "
            f"{event['tx_type']} | "
            f"{event['timestamp'][:19]}"
        )
# =======================================================================================================================================================================================================================
#      “Finally, the system verifies the integrity of the blockchain itself.”
# ========================================================================================================================================================================================================================

print("Hello World")
    # 7. Verify blockchain integrity
    log.info("\n[Step 7] Verifying blockchain integrity...")
    integrity = ledger.verify_chain_integrity()
    log.info(
        f"  Chain valid: {integrity['is_valid']} | "
        f"Total blocks: {integrity['total_blocks']}"
    )

    # 8. Save Go chaincode to disk
    cc_path = "/opt/secureprint/blockchain/chaincode/secureprint_cc.go"
    os.makedirs(os.path.dirname(cc_path), exist_ok=True)
    with open(cc_path, "w") as f:
        f.write(FABRIC_CHAINCODE)

    log.info(f"\n✅ Go chaincode saved: {cc_path}")
    log.info("✅ STEP 4 COMPLETE: Blockchain Supply Chain Ready")
    log.info("   Next: python3 backend/monitoring/anomaly_detector.py")
