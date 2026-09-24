import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import ProtectedRoute from "./ProtectedRoute";

const authState = { status: "anonymous", can: () => false };
vi.mock("../hooks/useAuth", () => ({ useAuth: () => authState }));

function renderAt(permission) {
  return render(
    <MemoryRouter initialEntries={["/secret"]}>
      <Routes>
        <Route path="/login" element={<div>login page</div>} />
        <Route
          path="/secret"
          element={
            <ProtectedRoute permission={permission}>
              <div>secret content</div>
            </ProtectedRoute>
          }
        />
      </Routes>
    </MemoryRouter>,
  );
}

describe("ProtectedRoute", () => {
  it("redirects anonymous users to /login", () => {
    authState.status = "anonymous";
    renderAt(null);
    expect(screen.getByText("login page")).toBeInTheDocument();
    expect(screen.queryByText("secret content")).not.toBeInTheDocument();
  });

  it("shows content to authenticated users", () => {
    authState.status = "authenticated";
    renderAt(null);
    expect(screen.getByText("secret content")).toBeInTheDocument();
  });

  it("shows an access-denied panel when the permission is missing", () => {
    authState.status = "authenticated";
    authState.can = () => false;
    renderAt("audit:view");
    expect(screen.getByRole("alert")).toHaveTextContent("Access denied");
    expect(screen.queryByText("secret content")).not.toBeInTheDocument();
  });
});
