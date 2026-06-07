export class ApiError extends Error {
  readonly status: number;
  readonly detail: string | null;
  readonly body: unknown;
  readonly requestId: string | null;

  constructor(
    status: number,
    message: string,
    detail: string | null = null,
    body: unknown = null,
    requestId: string | null = null,
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
    this.body = body;
    this.requestId = requestId;
  }

  static async fromResponse(response: Response, fallback = "Request failed"): Promise<ApiError> {
    const requestId = response.headers.get("X-Request-ID");
    const text = await response.text().catch(() => "");
    if (!text.trim()) {
      return new ApiError(response.status, `${fallback} (${response.status})`, null, null, requestId);
    }

    try {
      const parsed = JSON.parse(text) as {
        detail?: unknown;
        message?: unknown;
        error?: { message?: unknown; request_id?: unknown };
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
        requestId || (typeof parsed.error?.request_id === "string" ? parsed.error.request_id : null),
      );
    } catch {
      return new ApiError(response.status, text, null, text, requestId);
    }
  }
}
