const MARK_DONE_KEY = 'listenQueue.markDoneOnFinish';

export function getMarkDoneOnFinish(): boolean {
  const stored = localStorage.getItem(MARK_DONE_KEY);
  return stored === null ? true : stored === 'true';
}

export function setMarkDoneOnFinish(value: boolean): void {
  localStorage.setItem(MARK_DONE_KEY, String(value));
}
