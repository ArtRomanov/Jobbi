import { ApiError, getErrorMessage, handleApiError } from "@/shared/api";

const GENERIC = "Something went wrong. Please try again.";
const NETWORK = "Network error. Check your connection.";

describe("getErrorMessage", () => {
  it("returns a string detail from a 4xx body", () => {
    const error = new ApiError("x", 409, { detail: "Already in your sources" });
    expect(getErrorMessage(error)).toBe("Already in your sources");
  });

  it("returns the first message of a FastAPI 422 array detail", () => {
    const error = new ApiError("x", 422, {
      detail: [
        { loc: ["body", "input"], msg: "Field required", type: "missing" },
        { loc: ["body", "other"], msg: "Second", type: "missing" },
      ],
    });
    expect(getErrorMessage(error)).toBe("Field required");
  });

  it("falls back to the generic message for a body without a usable detail", () => {
    expect(getErrorMessage(new ApiError("x", 400, null))).toBe(GENERIC);
    expect(getErrorMessage(new ApiError("x", 400, { detail: "" }))).toBe(GENERIC);
    expect(getErrorMessage(new ApiError("x", 422, { detail: [] }))).toBe(GENERIC);
    expect(getErrorMessage(new ApiError("x", 400, { detail: { nested: true } }))).toBe(GENERIC);
  });

  it("does not show a 5xx detail", () => {
    expect(getErrorMessage(new ApiError("x", 500, { detail: "boom" }))).toBe(GENERIC);
  });

  it("treats non-API errors as network errors", () => {
    expect(getErrorMessage(new TypeError("Failed to fetch"))).toBe(NETWORK);
    expect(getErrorMessage("weird")).toBe(NETWORK);
  });
});

describe("handleApiError", () => {
  it("prefers the caller's status message over a 4xx string detail", () => {
    const showToast = vi.fn();
    handleApiError(new ApiError("x", 409, { detail: "Already in your sources" }), showToast, {
      409: "Custom",
    });
    expect(showToast).toHaveBeenCalledWith("Custom", "error");
  });

  it("falls back to a 4xx string detail when no status message matches", () => {
    const showToast = vi.fn();
    handleApiError(new ApiError("x", 409, { detail: "Already in your sources" }), showToast, {
      400: "Custom",
    });
    expect(showToast).toHaveBeenCalledWith("Already in your sources", "error");
  });

  it("uses the status handler when there is no string detail", () => {
    const showToast = vi.fn();
    handleApiError(new ApiError("x", 422, { detail: [{ msg: "bad" }] }), showToast, {
      422: "Please check your input and try again.",
    });
    expect(showToast).toHaveBeenCalledWith("Please check your input and try again.", "error");
  });

  it("shows the generic message for a 5xx and the network message otherwise", () => {
    const showToast = vi.fn();
    handleApiError(new ApiError("x", 500, { detail: "boom" }), showToast);
    handleApiError(new TypeError("Failed to fetch"), showToast);
    expect(showToast).toHaveBeenNthCalledWith(1, GENERIC, "error");
    expect(showToast).toHaveBeenNthCalledWith(2, NETWORK, "error");
  });
});
