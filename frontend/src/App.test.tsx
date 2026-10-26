import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";

function response(payload: unknown): { ok: boolean; status: number; json: () => Promise<unknown> } {
  return { ok: true, status: 200, json: async () => payload };
}

describe("AutoGrader dashboard shell", () => {
  beforeEach(() => {
    window.location.hash = "#/overview";
    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("/health/dependencies"))
          return Promise.resolve(response({ dependencies: [] }));
        if (url.includes("/assignments")) return Promise.resolve(response([]));
        return Promise.resolve(response({}));
      }),
    );
  });

  it("explains the first-run workflow and navigates through the dashboard", async () => {
    render(<App />);
    expect(
      await screen.findByRole("heading", { name: /Grade C submissions with evidence/i }),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Assignments/ }));
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: "Assignments" })).toBeInTheDocument(),
    );
    expect(screen.getByLabelText("JSON rules / rubric")).toBeInTheDocument();
  });
});
