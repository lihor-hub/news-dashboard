export interface PublicDifyConfig {
  enabled: boolean;
  base_url: string | null;
  app_token: string | null;
  title: string | null;
}

export interface PublicConfig {
  dify: PublicDifyConfig;
}

const LOOPBACK_HOSTS = new Set(['localhost', '127.0.0.1', '[::1]']);
const CONTROL_OR_FORMAT_CHARACTER = /[\p{Cc}\p{Cf}]/u;

function isValidText(value: unknown, maxLength: number): value is string {
  if (typeof value !== 'string') return false;
  const codePointLength = Array.from(value).length;
  return (
    codePointLength > 0 && codePointLength <= maxLength && !CONTROL_OR_FORMAT_CHARACTER.test(value)
  );
}

function isValidBaseUrl(value: unknown): value is string {
  if (!isValidText(value, 2_048) || value.endsWith('/')) return false;

  try {
    const url = new URL(value);
    return (
      (url.protocol === 'https:' ||
        (url.protocol === 'http:' && LOOPBACK_HOSTS.has(url.hostname))) &&
      url.origin !== window.location.origin &&
      !url.username &&
      !url.password &&
      !url.search &&
      !url.hash
    );
  } catch {
    return false;
  }
}

function isPublicDifyConfig(value: unknown): value is PublicDifyConfig {
  if (!value || typeof value !== 'object') return false;

  const dify = value as Record<string, unknown>;
  if (dify.enabled === false) {
    return (
      dify.base_url === null &&
      dify.app_token === null &&
      (dify.title === null || isValidText(dify.title, 120))
    );
  }

  return (
    dify.enabled === true &&
    isValidBaseUrl(dify.base_url) &&
    isValidText(dify.app_token, 512) &&
    isValidText(dify.title, 120)
  );
}

function isPublicConfig(value: unknown): value is PublicConfig {
  return (
    !!value &&
    typeof value === 'object' &&
    isPublicDifyConfig((value as Record<string, unknown>).dify)
  );
}

export async function fetchPublicConfig(): Promise<PublicConfig> {
  const response = await fetch('/api/config', { credentials: 'same-origin' });
  if (!response.ok) throw new Error('Unable to load public configuration');

  const config: unknown = await response.json();
  if (!isPublicConfig(config)) throw new Error('Invalid public configuration');
  return config;
}
