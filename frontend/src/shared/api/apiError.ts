export class ApiError extends Error {
  readonly status: number;
  readonly code: string | null;
  readonly detail: string | null;
  readonly details: Record<string, unknown>;
  readonly body: unknown;
  readonly requestId: string | null;
  readonly schemaVersion: string | null;

  constructor(
    status: number,
    message: string,
    detail: string | null = null,
    body: unknown = null,
    requestId: string | null = null,
    code: string | null = null,
    details: Record<string, unknown> = {},
    schemaVersion: string | null = null,
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.detail = detail;
    this.details = details;
    this.body = body;
    this.requestId = requestId;
    this.schemaVersion = schemaVersion;
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
        error?: {
          code?: unknown;
          message?: unknown;
          fields?: unknown;
          details?: unknown;
          trace_id?: unknown;
          request_id?: unknown;
        };
      };
      const errorDetails =
        parsed.error?.fields && typeof parsed.error.fields === "object"
          ? (parsed.error.fields as Record<string, unknown>)
          : parsed.error?.details && typeof parsed.error.details === "object"
            ? (parsed.error.details as Record<string, unknown>)
            : {};
      const code =
        typeof parsed.error?.code === "string" ? parsed.error.code : null;
      const detail =
        typeof parsed.error?.message === "string"
          ? parsed.error.message
          : typeof parsed.detail === "string"
            ? parsed.detail
            : typeof parsed.message === "string"
              ? parsed.message
              : null;
      return new ApiError(
        response.status,
        detail ?? text,
        detail,
        parsed,
        requestId ||
          (typeof parsed.error?.trace_id === "string"
            ? parsed.error.trace_id
            : typeof parsed.error?.request_id === "string"
              ? parsed.error.request_id
              : null),
        code,
        errorDetails,
        response.headers.get("X-Agriculture-Schema-Version"),
      );
    } catch {
      return new ApiError(response.status, text, null, text, requestId);
    }
  }
}
