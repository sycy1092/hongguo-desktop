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
  const ready = (quality: string) =>
    bridge
      .request<{ ready: boolean }>('/media/probe', {
        method: 'POST',
        body: { seriesId, episode, quality },
        timeout: 4000,
      })
      .then(value => !!value?.ready)
      .catch(() => false);
  // 先找本地已有的档位（任何一档都比现下快），再按降档顺序回退。
  const candidates: string[] = [];
  let current = preferred;
  for (let step = 0; step < 3; step += 1) {
    if (!candidates.includes(current)) candidates.push(current);
    const next = downgrade(current);
    if (next === current) break;
    current = next;
  }
  for (const quality of candidates) {
    if (await ready(quality)) return quality;
  }
  return downgrade(preferred);
}
