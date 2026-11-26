const baseUrl =
  import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly body: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError;
}

function serializeJson(body: unknown): string | undefined {
  return body !== undefined ? JSON.stringify(body) : undefined;
}

/** Extra fetch options a caller may need. */
export interface RequestOptions {
  /** Let the request outlive the page (e.g. sent from `pagehide`). */
  keepalive?: boolean;
}

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
  options: RequestOptions = {},
): Promise<T> {
  // FormData sets its own multipart Content-Type (with the boundary).
  const isForm = body instanceof FormData;
  const headers: Record<string, string> = isForm
    ? {}
    : { "Content-Type": "application/json" };

  const token = localStorage.getItem("jobbi_token");
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const response = await fetch(`${baseUrl}${path}`, {
    method,
    headers,
    body: isForm ? body : serializeJson(body),
    ...(options.keepalive ? { keepalive: true } : {}),
  });

  const data: unknown = await response.json().catch(() => null);

  if (!response.ok) {
    throw new ApiError(
      `Request failed: ${method} ${path} (${String(response.status)})`,
      response.status,
      data,
    );
  }

  return data as T;
}

export const apiClient = {
  get: <T>(path: string): Promise<T> => request<T>("GET", path),
  post: <T>(path: string, body: unknown): Promise<T> =>
    request<T>("POST", path, body),
  /** Multipart POST, e.g. a file upload. */
  postForm: <T>(path: string, form: FormData): Promise<T> =>
    request<T>("POST", path, form),
  patch: <T>(path: string, body: unknown): Promise<T> =>
    request<T>("PATCH", path, body),
  delete: <T>(path: string, options?: RequestOptions): Promise<T> =>
    request<T>("DELETE", path, undefined, options),
};
