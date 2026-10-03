import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "../services/api";
import CompliancePage from "./CompliancePage";

vi.mock("../services/api");

const control = (over) => ({
  id: 1, framework: "NIST", control_ref: "PR.AC-1", title: "Credentials are managed",
  description: "Passwords hashed.", status: "PASS", evidence: "All 6 users store Argon2 hashes",
  last_checked: "2026-10-04T00:00:00Z", ...over,
});
const report = (controls) => ({
  generated_at: "2026-10-04T00:00:00Z", disclaimer: "Not a certification.",
  pass_count: controls.filter((c) => c.status === "PASS").length,
  fail_count: controls.filter((c) => c.status === "FAIL").length,
  unknown_count: controls.filter((c) => c.status === "UNKNOWN").length,
  total: controls.length, controls,
});

describe("CompliancePage", () => {
  beforeEach(() => vi.resetAllMocks());

  it("shows stored controls with evidence, counts and the disclaimer", async () => {
    api.complianceControls.mockResolvedValue(report([
      control({}), control({ id: 2, control_ref: "8.5.2", framework: "ISO9001", status: "UNKNOWN",
        title: "Traceability", evidence: "No parts registered yet" }),
    ]));
    render(<CompliancePage />);
    expect(await screen.findByText("Credentials are managed")).toBeInTheDocument();
    expect(screen.getByText(/All 6 users store Argon2 hashes/)).toBeInTheDocument();
    expect(screen.getByText("1 passing")).toBeInTheDocument();
    expect(screen.getByText("1 not yet verifiable")).toBeInTheDocument();
    expect(screen.getByRole("note")).toHaveTextContent("Not a certification.");
  });

  it("runs the checks and shows a FAIL result", async () => {
    api.complianceControls.mockResolvedValue(report([]));
    api.runCompliance.mockResolvedValue(report([
      control({ status: "FAIL", evidence: "Audit chain broken at entry 3" }),
    ]));
    render(<CompliancePage />);
    fireEvent.click(await screen.findByRole("button", { name: /run checks now/i }));
    expect(await screen.findByText(/Audit chain broken at entry 3/)).toBeInTheDocument();
    expect(screen.getByText("1 failing")).toBeInTheDocument();
  });

  it("shows an error when the backend refuses", async () => {
    api.complianceControls.mockRejectedValue(new Error("Permission denied"));
    render(<CompliancePage />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Permission denied");
  });
});
