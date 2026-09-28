import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "../services/api";
import QualityPage from "./QualityPage";

const authState = { can: () => true };
vi.mock("../hooks/useAuth", () => ({ useAuth: () => authState }));
vi.mock("../services/api");

const INSPECT_RESULT = {
  inspection_id: 1, status: "defect_detected", defect_type: "LAYER_SHIFT",
  confidence: 0.93, severity: "high",
  class_probabilities: { NORMAL: 0.02, WARPING: 0.01, STRINGING: 0.01, LAYER_SHIFT: 0.93, CLOGGING: 0.03 },
  model_version: "defect-rf-test", created_at: "2026-01-01T00:00:00Z",
  cv_report: {
    target_size: 96, edge_density: 0.12, sharpness_variance: 88.4, contour_count: 40,
    original_png_base64: "aGVsbG8=", edges_png_base64: "aGVsbG8=", contours_png_base64: "aGVsbG8=",
    quality_flags: [],
  },
};

describe("QualityPage", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    api.qualityHistory.mockResolvedValue({ total: 0, limit: 15, offset: 0, items: [] });
  });

  it("runs an inspection and shows the result", async () => {
    api.inspectImage.mockResolvedValue(INSPECT_RESULT);
    render(<QualityPage />);
    const file = new File(["x"], "print.png", { type: "image/png" });
    const input = document.querySelector('input[type="file"]');
    fireEvent.change(input, { target: { files: [file] } });
    fireEvent.click(screen.getByRole("button", { name: /inspect image/i }));
    const result = await screen.findByTestId("inspect-result");
    expect(result).toHaveTextContent("DEFECT DETECTED");
    expect(result).toHaveTextContent("LAYER_SHIFT");
    expect(result).toHaveTextContent("93.0%");
    await waitFor(() => expect(api.qualityHistory).toHaveBeenCalled());
  });

  it("predicts process quality and shows risk level", async () => {
    api.predictProcessQuality.mockResolvedValue({
      predicted_quality: "poor", quality_probabilities: { good: 0.05, fair: 0.15, poor: 0.8 },
      anomaly_score: 0.9, is_anomaly: true, risk_level: "HIGH", model_version: "process-rf-test",
      out_of_range_parameters: { nozzle_temp_c: { value: 280, safe_range: [190, 220] } },
    });
    render(<QualityPage />);
    fireEvent.click(screen.getByRole("button", { name: /load suspicious/i }));
    fireEvent.click(screen.getByRole("button", { name: /predict quality/i }));
    const result = await screen.findByTestId("predict-result");
    expect(result).toHaveTextContent("HIGH");
    expect(result).toHaveTextContent("nozzle_temp_c");
    expect(api.predictProcessQuality).toHaveBeenCalledWith(
      expect.objectContaining({ nozzle_temp_c: 280, speed_mm_s: 250 }),
    );
  });
});
