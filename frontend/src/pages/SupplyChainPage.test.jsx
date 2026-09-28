import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { WORKFLOW_STEPS } from "../components/supplychain/workflow";
import { api } from "../services/api";
import SupplyChainPage from "./SupplyChainPage";

const authState = { can: () => true };
vi.mock("../hooks/useAuth", () => ({ useAuth: () => authState }));
vi.mock("../services/api");

const PART = {
  id: 1, part_code: "PART-000001", design_id: 1, design_code: "SP-3D-000001",
  design_hash: "abc", batch: "B1", material: "PLA", printer_id: null,
  manufactured_at: null, quality_result: null, status: "DESIGN_CREATED",
  created_at: "2026-01-01T00:00:00Z",
};

const DETAIL = {
  part: PART,
  events: [{
    event_id: "EVT-PART-000001-0001", sequence: 1, action: "DESIGN_CREATED", status: "COMPLETED",
    actor: "engineer1", timestamp: "2026-01-01T00:00:00Z", payload: null,
    prev_hash: "0".repeat(64), hash: "a".repeat(64), signature: "b".repeat(128),
  }],
  chain_verification: { valid: true, checked: 1, first_broken_event: null, reason: null },
};

describe("workflow constants", () => {
  it("lists the nine steps in the specified order", () => {
    expect(WORKFLOW_STEPS).toEqual([
      "DESIGN_CREATED", "DESIGN_APPROVED", "SLICED", "PRINT_STARTED", "QUALITY_INSPECTED",
      "QUALITY_APPROVED", "CERTIFIED", "SHIPPED", "RECEIVED",
    ]);
  });
});

describe("SupplyChainPage", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    api.listDesigns.mockResolvedValue([]);
    api.listParts.mockResolvedValue([PART]);
    api.getPart.mockResolvedValue(DETAIL);
  });

  it("lists parts and shows the provenance timeline for a selected part", async () => {
    render(<SupplyChainPage />);
    fireEvent.click(await screen.findByText("PART-000001"));
    expect(await screen.findByText(/Provenance · PART-000001/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /advance: design_approved/i })).toBeInTheDocument();
  });

  it("shows an INTEGRITY FAILURE naming the broken event when verification fails", async () => {
    api.verifyPartChain.mockResolvedValue({
      valid: false, checked: 1, first_broken_event: 1,
      reason: "Record contents do not match the stored hash",
    });
    render(<SupplyChainPage />);
    fireEvent.click(await screen.findByText("PART-000001"));
    fireEvent.click(await screen.findByRole("button", { name: /verify chain/i }));
    expect(await screen.findByRole("status")).toHaveTextContent("INTEGRITY FAILURE at event #1");
  });

  it("shows the authentication verdict returned by the backend", async () => {
    api.authenticatePart.mockResolvedValue({
      verdict: "TAMPERED", part: PART, reason: "Provenance chain integrity failure at event #1",
      chain_verification: { valid: false, checked: 1, first_broken_event: 1, reason: "x" },
    });
    render(<SupplyChainPage />);
    fireEvent.change(screen.getByPlaceholderText("PART-000001"), { target: { value: "PART-000001" } });
    fireEvent.click(screen.getByRole("button", { name: /^authenticate$/i }));
    const result = await screen.findByTestId("authenticate-result");
    expect(result).toHaveTextContent("TAMPERED");
    await waitFor(() => expect(api.authenticatePart).toHaveBeenCalledWith("PART-000001"));
  });
});
