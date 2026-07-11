import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";

vi.mock("./lib/api", () => ({
  APIError: class APIError extends Error {},
  api: {
    health: vi.fn().mockResolvedValue(true),
    getTransaction: vi.fn(),
  },
}));

describe("single-chat commerce experience", () => {
  beforeEach(() => localStorage.clear());

  it("starts with one conversational composer and the canonical demo shortcut", () => {
    render(<App />);

    expect(screen.getByRole("heading", { name: "What can I take care of?" })).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Message the commerce agent" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /try the demo request/i })).toBeInTheDocument();
  });
});
