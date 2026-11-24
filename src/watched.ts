/** Local "已播放" bookkeeping for the episode picker.
 *
 * The upstream list only tells us the latest episode per series, so watched
 * episodes are remembered on this machine (per series, capped and sorted).
 */
const PREFIX = 'watched:';
const LIMIT = 4000;

export function watchedKey(seriesId: string): string {
  return `${PREFIX}${seriesId}`;
}

export function parseWatched(raw: string | null | undefined): number[] {
  if (!raw) return [];
  try {
    const value = JSON.parse(raw);
    if (!Array.isArray(value)) return [];
    return [...new Set(value.filter(item => Number.isInteger(item) && item > 0 && item <= 100000))].sort((a, b) => a - b);
  } catch {
    return [];
  }
}

export function loadWatched(seriesId: string, storage: Pick<Storage, 'getItem'> | undefined = globalThis.localStorage): number[] {
  if (!seriesId || !storage) return [];
  try {
    return parseWatched(storage.getItem(watchedKey(seriesId)));
  } catch {
    return [];
  }
}

export function saveWatched(seriesId: string, values: Iterable<number>,
  storage: Pick<Storage, 'setItem'> | undefined = globalThis.localStorage): number[] {
  const sorted = [...new Set([...values].filter(item => Number.isInteger(item) && item > 0))].sort((a, b) => a - b).slice(-LIMIT);
  if (seriesId && storage) {
    try { storage.setItem(watchedKey(seriesId), JSON.stringify(sorted)); } catch { /* 无存储权限时只内存生效 */ }
  }
  return sorted;
}

export function markWatched(seriesId: string, episode: number, current: Iterable<number>,
  storage: Pick<Storage, 'getItem' | 'setItem'> | undefined = globalThis.localStorage): number[] {
  if (!seriesId || !Number.isInteger(episode) || episode <= 0) return [...current];
  return saveWatched(seriesId, [...current, episode], storage);
}
