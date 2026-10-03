import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "../services/api";
import AuditLogsPage from "./AuditLogsPage";

vi.mock("../services/api");

const row = (id) => ({
  id, timestamp: "2026-10-04T00:00:00Z", user: "admin", action: "LOGIN", resource: "auth",
  ip: null, result: "SUCCESS", severity: "INFO", details: null,
  prev_hash: "0".repeat(64), event_hash: "a".repeat(64),
});

describe("AuditLogsPage", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    api.auditLogs.mockResolvedValue({ total: 1, limit: 25, offset: 0, items: [row(1)] });
  });

  it("lists entries", async () => {
    render(<AuditLogsPage />);
    expect(await screen.findByText("LOGIN")).toBeInTheDocument();
    expect(screen.getByText("Entries (1)")).toBeInTheDocument();
  });

  it("re-queries with the chosen result filter", async () => {
    render(<AuditLogsPage />);
    await screen.findByText("LOGIN");
    fireEvent.change(screen.getByLabelText("Result"), { target: { value: "FAILURE" } });
    await waitFor(() =>
      expect(api.auditLogs).toHaveBeenLastCalledWith(
        expect.objectContaining({ result: "FAILURE", offset: 0 }), expect.anything()));
  });

  it("reports an integrity failure naming the broken entry", async () => {
    api.verifyAuditChain.mockResolvedValue({ valid: false, checked: 5, first_broken_id: 3, reason: "hash mismatch" });
    render(<AuditLogsPage />);
    fireEvent.click(await screen.findByRole("button", { name: /verify chain/i }));
    expect(await screen.findByRole("status")).toHaveTextContent("INTEGRITY FAILURE at entry #3");
  });

  it("confirms an intact chain", async () => {
    api.verifyAuditChain.mockResolvedValue({ valid: true, checked: 28, first_broken_id: null, reason: null });
    render(<AuditLogsPage />);
    fireEvent.click(await screen.findByRole("button", { name: /verify chain/i }));
    expect(await screen.findByRole("status")).toHaveTextContent("28 entries verified");
  });
});
