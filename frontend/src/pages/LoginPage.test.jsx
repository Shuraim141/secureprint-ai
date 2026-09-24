import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../services/api";
import LoginPage from "./LoginPage";

const authState = { status: "anonymous", login: vi.fn() };
vi.mock("../hooks/useAuth", () => ({ useAuth: () => authState }));

function renderPage() {
  return render(
    <MemoryRouter>
      <LoginPage />
    </MemoryRouter>,
  );
}

describe("LoginPage", () => {
  beforeEach(() => {
    authState.login = vi.fn();
  });

  it("submits the entered credentials to login()", async () => {
    authState.login.mockResolvedValue(undefined);
    renderPage();
    fireEvent.change(screen.getByLabelText(/username/i), { target: { value: "engineer1" } });
    fireEvent.change(screen.getByLabelText(/password/i), { target: { value: "secret-pass-1" } });
    fireEvent.click(screen.getByRole("button", { name: /sign in/i }));
    await waitFor(() => expect(authState.login).toHaveBeenCalledWith("engineer1", "secret-pass-1"));
  });

  it("shows the server's error message when login fails", async () => {
    authState.login.mockRejectedValue(new ApiError(401, "Invalid username or password"));
    renderPage();
    fireEvent.change(screen.getByLabelText(/username/i), { target: { value: "x" } });
    fireEvent.change(screen.getByLabelText(/password/i), { target: { value: "y" } });
    fireEvent.click(screen.getByRole("button", { name: /sign in/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid username or password");
  });
});
