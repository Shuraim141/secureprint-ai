import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "../services/api";
import ManufacturingPage from "./ManufacturingPage";

const authState = { can: () => true };
vi.mock("../hooks/useAuth", () => ({ useAuth: () => authState }));
vi.mock("../services/api");

const PRINTER = {
  id: 1, printer_code: "PRINTER-01", name: "Prusa-style FDM Printer 1", adapter: "simulator",
  db_state: "idle", simulator_state: "IDLE", scenario: null, current_job_id: null,
};

describe("ManufacturingPage", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    api.listPrinters.mockResolvedValue([PRINTER]);
    api.listIncidents.mockResolvedValue({ total: 0, limit: 10, offset: 0, items: [] });
    api.getTelemetry.mockResolvedValue({ printer_id: 1, simulator_state: "IDLE", samples: [] });
  });

  it("lists printers without violating React's Rules of Hooks when the list is empty on first render", async () => {
    // The first render has printers.data === null (before the fetch resolves), so zero
    // PrinterCards mount; after the fetch resolves, one PrinterCard mounts. This must not throw
    // a "Rendered fewer/more hooks than expected" error.
    render(<ManufacturingPage />);
    expect(await screen.findByText(/PRINTER-01/)).toBeInTheDocument();
  });

  it("starts a print with the selected scenario", async () => {
    api.startPrint.mockResolvedValue({ ...PRINTER, simulator_state: "RUNNING" });
    render(<ManufacturingPage />);
    await screen.findByText(/PRINTER-01/);
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "OVERHEAT" } });
    fireEvent.click(screen.getByRole("button", { name: /^start$/i }));
    // PrinterCard calls api.startPrint(printer.id, scenario) -- no seed argument -- so
    // the mock is called with exactly 2 arguments, not 3 with an explicit undefined.
    await waitFor(() => expect(api.startPrint).toHaveBeenCalledWith(1, "OVERHEAT"));
  });

  it("shows live telemetry including an anomaly badge", async () => {
    api.getTelemetry.mockResolvedValue({
      printer_id: 1, simulator_state: "PAUSED",
      samples: [
        { tick: 0, temperature: 205, bed_temperature: 60, speed: 50, flow_rate: 100, layer: 1,
          total_layers: 40, progress: 2.5, power: 48, anomaly: false, risk: "NONE" },
        { tick: 1, temperature: 280, bed_temperature: 60, speed: 50, flow_rate: 100, layer: 1,
          total_layers: 40, progress: 5.0, power: 90, anomaly: true, risk: "HIGH" },
      ],
    });
    render(<ManufacturingPage />);
    expect(await screen.findByText(/ANOMALY: HIGH/)).toBeInTheDocument();
  });

  it("analyzes an uploaded G-code file and shows the risk", async () => {
    api.analyzeGcode.mockResolvedValue({
      id: 1, filename: "bad.gcode", sha256: "x", safe: false, risk: "HIGH",
      findings: [{ line: 2, severity: "HIGH", code: "EXCESSIVE_NOZZLE_TEMPERATURE",
                  message: "M104 sets nozzle to 280.0C (safe range 190-220C)" }],
      stats: { total_lines: 5, move_commands: 2, max_nozzle_temp_c: 280, max_feed_rate_mm_s: 50 },
      created_at: "2026-01-01T00:00:00Z",
    });
    render(<ManufacturingPage />);
    const file = new File(["M104 S280"], "bad.gcode");
    const input = document.querySelector('input[type="file"]');
    fireEvent.change(input, { target: { files: [file] } });
    fireEvent.submit(input.closest("form")); // required-field submit workaround, see QualityPage.test.jsx
    const result = await screen.findByTestId("gcode-result");
    expect(result).toHaveTextContent("SECURITY WARNING");
    expect(result).toHaveTextContent("EXCESSIVE_NOZZLE_TEMPERATURE");
  });

  it("lists security incidents", async () => {
    api.listIncidents.mockResolvedValue({
      total: 1, limit: 10, offset: 0,
      items: [{ id: 1, incident_code: "INC-00001", incident_type: "PARAMETER_TAMPERING",
               severity: "HIGH", printer_id: 1, print_job_id: 1, action_taken: "PRINT_PAUSED",
               status: "OPEN", description: "Nozzle temperature exceeded threshold",
               opened_at: "2026-01-01T00:00:00Z", resolved_at: null }],
    });
    render(<ManufacturingPage />);
    expect(await screen.findByText("INC-00001")).toBeInTheDocument();
    expect(screen.getByText(/Nozzle temperature exceeded threshold/)).toBeInTheDocument();
  });
});
