export async function readErrorMessage(response: Response): Promise<string> {
  try {
    const body: unknown = await (response.json() as Promise<unknown>);
    if (body && typeof body === 'object') {
      const { detail, message } = body as Record<string, unknown>;
      if (typeof detail === 'string' && detail) return detail;
      if (Array.isArray(detail) && detail.length > 0) {
        const msgs = detail
          .map((d) => (d && typeof d === 'object' ? (d as Record<string, unknown>).msg : null))
          .filter((m): m is string => typeof m === 'string');
        if (msgs.length > 0) return msgs.join('; ');
      }
      if (typeof message === 'string' && message) return message;
    }
  } catch {
    // non-JSON body — fall through
  }
  return `${response.status} ${response.statusText}`;
}

export class HttpError extends Error {
  constructor(
    public readonly status: number,
    message: string
  ) {
    super(message);
    this.name = 'HttpError';
  }
}

export const sessionExpiredEvent = 'news-dashboard:session-expired';

function shouldEmitSessionExpired(url: string): boolean {
  return url.startsWith('/api/') && !url.startsWith('/api/auth/');
}

export async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    credentials: 'same-origin',
    ...init,
  });
  if (!response.ok) {
    const error = new HttpError(response.status, await readErrorMessage(response));
    if (response.status === 401 && shouldEmitSessionExpired(url)) {
      window.dispatchEvent(new CustomEvent(sessionExpiredEvent, { detail: { url } }));
    }
    throw error;
  }
  return response.json() as Promise<T>;
}
