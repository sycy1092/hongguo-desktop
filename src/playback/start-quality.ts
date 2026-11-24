/** Shared rule for the quality a session should start with.
 *
 * The detail page preloads a session before the player mounts, and the player
 * creates its own session when switching. Both must pick the same quality or
 * the same episode gets downloaded twice on a slow link.
 */
type Transport = {
  request<T>(path: string, options?: { method?: string; body?: unknown; timeout?: number }): Promise<T>;
};

export const FAST_START_QUALITY = '720p';

export function downgrade(value: string): string {
  const resolution = Number(/\d+/.exec(value)?.[0] ?? 0);
  if (!resolution) return FAST_START_QUALITY;
  if (resolution >= 1080) return '720p';
  if (resolution >= 720) return '540p';
  return value;
}

export async function chooseStartQuality(
  bridge: Transport,
  seriesId: string,
  episode: number,
  preferred: string,
): Promise<string> {
  if (!['auto', '1080p', '720p', '540p'].includes(preferred)) return preferred;
  const ready = (quality: string) =>
    bridge
      .request<{ ready: boolean }>('/media/probe', {
        method: 'POST',
        body: { seriesId, episode, quality },
        timeout: 4000,
      })
      .then(value => !!value?.ready)
      .catch(() => false);
  if (await ready(preferred)) return preferred;
  const fallback = downgrade(preferred);
  if (fallback === preferred) return preferred;
  return fallback;
}
