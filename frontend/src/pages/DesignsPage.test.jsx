import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { api } from "../services/api";
import DesignsPage from "./DesignsPage";

const authState = { can: () => true };
vi.mock("../hooks/useAuth", () => ({ useAuth: () => authState }));
vi.mock("../services/api");

const DESIGN = {
  id: 1, design_code: "SP-3D-000001", name: "Bracket", owner: "engineer1", file_format: "stl",
  current_version: 1, is_4d: false, sha256: "abc", triangle_count: 224, encrypted: true,
};

describe("DesignsPage", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    api.listDesigns.mockResolvedValue([DESIGN]);
  });

  it("lists registered designs from the backend", async () => {
    render(
      <MemoryRouter>
        <DesignsPage />
      </MemoryRouter>,
    );
    expect(await screen.findByText("SP-3D-000001 · v1 · STL · 224 triangles · owner engineer1")).toBeInTheDocument();
  });

  it("loads and shows design detail when a design is selected", async () => {
    api.getDesign.mockResolvedValue({
      ...DESIGN,
      versions: [{
        version: 1, original_filename: "bracket.stl", file_size: 1200, sha256: "abc".repeat(20),
        encrypted: true, encryption_alg: "AES-256-GCM", created_by: "engineer1",
        created_at: "2026-01-01T00:00:00Z",
        analysis: {
          triangle_count: 224, vertex_count: 114, dimensions_mm: { x: 60, y: 30, z: 10 },
          volume_mm3: 18000, volume_reliable: true, surface_area_mm2: 6600, watertight: true,
          bounding_box_min: [0, 0, 0], bounding_box_max: [60, 30, 10], units_assumed: "mm",
          warnings: [],
        },
        fingerprints: [
          { kind: "sha256", value: "abc".repeat(20), meta: null },
          { kind: "geometric", value: "def".repeat(20), meta: null },
          { kind: "watermark", value: "wm", meta: { status: "applied", tag_hex: "aa", samples: 100, max_abs_change: 1e-6, note: "note" } },
        ],
      }],
      profile_4d: null,
      history: [{ time: "2026-01-01T00:00:00Z", actor: "engineer1", event: "DESIGN_REGISTERED", detail: "v1" }],
      warnings: [],
    });

    render(
      <MemoryRouter>
        <DesignsPage />
      </MemoryRouter>,
    );
    fireEvent.click(await screen.findByText(/SP-3D-000001 · v1 · STL/));  // fireEvent wraps state updates in act()
    expect(await screen.findByText("SP-3D-000001 · Bracket")).toBeInTheDocument();
    expect(await screen.findByText("224")).toBeInTheDocument(); // triangle count stat
    await waitFor(() => expect(api.getDesign).toHaveBeenCalledWith(1, expect.anything()));
  });
});
