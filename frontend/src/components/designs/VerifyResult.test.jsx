import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import VerifyResult from "./VerifyResult";

const AUTHENTIC = {
  filename: "a.stl", sha256: "abc123", verdict: "AUTHENTIC", headline: "AUTHENTIC: exact match",
  reasons: ["SHA-256 matches SP-3D-000001 v1"], match_type: "original",
  matched_design: { design_id: 1, design_code: "SP-3D-000001", name: "Bracket", version: 1 },
  checks: { sha256_match: true, geometric_match: false, watermark: null },
  differences: null, uploaded_analysis: null, uploaded_geometric_fingerprint: null,
};

const TAMPERED = {
  ...AUTHENTIC, verdict: "TAMPERED", headline: "TAMPERED: fingerprint mismatch",
  reasons: ["SHA-256 differs", "Geometric fingerprint differs"],
  checks: { sha256_match: false, geometric_match: false, watermark: { detected: true, score: 1 } },
  differences: {
    changed: ["volume_mm3"],
    metrics: {
      volume_mm3: { registered: 18000, uploaded: 18150, delta: 150, delta_pct: 0.83, changed: true },
      triangle_count: { registered: 224, uploaded: 224, delta: 0, delta_pct: 0, changed: false },
    },
  },
};

describe("VerifyResult", () => {
  it("shows AUTHENTIC with matched checks", () => {
    render(<VerifyResult result={AUTHENTIC} />);
    expect(screen.getByTestId("verdict")).toHaveTextContent("AUTHENTIC");
    expect(screen.getByText(/SHA-256 matches SP-3D-000001/)).toBeInTheDocument();
  });

  it("shows TAMPERED with a differences table highlighting the changed metric", () => {
    render(<VerifyResult result={TAMPERED} />);
    expect(screen.getByTestId("verdict")).toHaveTextContent("TAMPERED");
    const table = screen.getByTestId("differences");
    expect(table).toHaveTextContent("18,000");  // formatNumber() uses toLocaleString()
    expect(table).toHaveTextContent("18,150");
    expect(table).toHaveTextContent("unchanged"); // triangle_count row
  });
});
