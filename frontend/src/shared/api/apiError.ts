export class ApiError extends Error {
  readonly status: number;
  readonly detail: string | null;
  readonly body: unknown;

  constructor(status: number, message: string, detail: string | null = null, body: unknown = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
    this.body = body;
  }

  static async fromResponse(response: Response, fallback = "Request failed"): Promise<ApiError> {
    const text = await response.text().catch(() => "");
    if (!text.trim()) {
      return new ApiError(response.status, `${fallback} (${response.status})`);
    }

    try {
      const parsed = JSON.parse(text) as {
        detail?: unknown;
        message?: unknown;
        error?: { message?: unknown };
      };
      const detail =
        typeof parsed.detail === "string"
          ? parsed.detail
          : typeof parsed.message === "string"
            ? parsed.message
            : typeof parsed.error?.message === "string"
              ? parsed.error.message
              : null;
      return new ApiError(
        response.status,
        detail ?? text,
        detail,
        parsed,
      );
    } catch {
      return new ApiError(response.status, text, null, text);
    }
  }
}
