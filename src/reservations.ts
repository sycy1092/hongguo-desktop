import type { ReservationHistoryEntry, ReservationItem, ReservationList } from '../shared/contracts';

/** Calendar keys are the server's own YYYYMMDD day strings (Asia/Shanghai). */
export type ReservationDay = { key: string; label: string; sub: string };

const WEEKDAYS = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'];

function parts(key: string): { year: number; month: number; day: number } | null {
  if (!/^\d{8}$/.test(key)) return null;
  const year = Number(key.slice(0, 4)), month = Number(key.slice(4, 6)), day = Number(key.slice(6));
  if (month < 1 || month > 12 || day < 1 || day > 31) return null;
  return { year, month, day };
}

function utc(key: string): number | null {
  const value = parts(key);
  return value ? Date.UTC(value.year, value.month - 1, value.day) : null;
}

/** Whole days from `today` to `key`; null when either key is not a real day. */
export function dayDistance(key: string, today: string): number | null {
  const target = utc(key), base = utc(today);
  if (target === null || base === null) return null;
  return Math.round((target - base) / 86400000);
}

export function dayLabel(key: string, today: string): ReservationDay {
  const value = parts(key);
  if (!value) return { key, label: key, sub: '' };
  const sub = `${value.month}月${value.day}日`;
  const distance = dayDistance(key, today);
  if (distance === 0) return { key, label: '今天', sub };
  if (distance === 1) return { key, label: '明天', sub };
  if (distance === 2) return { key, label: '后天', sub };
  if (distance === -1) return { key, label: '昨天', sub };
  if (distance !== null && distance > 2 && distance <= 7) {
    return { key, label: WEEKDAYS[new Date(utc(key) as number).getUTCDay()], sub };
  }
  return { key, label: sub, sub: `${value.year}年` };
}

/** Drops the days that already passed and caps how many days are offered. */
export function upcomingDays(dates: string[], today: string, limit = 8): ReservationDay[] {
  const days: ReservationDay[] = [];
  for (const key of [...new Set(dates)].sort()) {
    const distance = dayDistance(key, today);
    if (distance === null || distance < 0) continue;
    days.push(dayLabel(key, today));
    if (days.length >= limit) break;
  }
  return days;
}

/** "预计11月23日上线" when the server said so, otherwise a date from the timestamp. */
export function publishLabel(item: ReservationItem): string {
  if (item.online) return item.publishAt > 0 ? `${stampLabel(item.publishAt)}上线` : '已上线';
  if (item.note) return item.note;
  if (item.publishAt > 0) return `${stampLabel(item.publishAt)}上线`;
  return '即将上线';
}

/** Unix seconds to a local month/day label; empty for an unset field. */
export function stampLabel(unix: number): string {
  if (!Number.isFinite(unix) || unix <= 0) return '';
  const date = new Date(unix * 1000);
  return `${date.getMonth() + 1}月${date.getDate()}日`;
}

export type HistoryState = 'cancelled' | 'launched' | 'upcoming';

/** A local record counts as launched when upstream said so, or when its scheduled
 * time had already passed the last time the account list was read. A delayed release
 * that upstream still lists as 待上线 is not flipped by the clock. */
export function historyState(entry: ReservationHistoryEntry, now: number): HistoryState {
  if (entry.cancelledAt > 0) return 'cancelled';
  if (entry.online) return 'launched';
  if (entry.publishAt > 0 && entry.publishAt <= now && entry.seenAt < entry.publishAt) return 'launched';
  return 'upcoming';
}

export const historyLabels: Record<HistoryState, string> = { cancelled: '已取消', launched: '已上线', upcoming: '待上线' };

export function seriesOfHistory(entry: ReservationHistoryEntry) {
  return { id: entry.seriesId, title: entry.title, cover: entry.cover, intro: '',
    totalEpisodes: entry.episodeCount, tags: [], actors: [] as string[] };
}

export function reservedIds(list: ReservationList | null): Set<string> {
  const ids = new Set<string>();
  for (const item of [...(list?.upcoming || []), ...(list?.online || [])]) {
    if (item.reservationId) ids.add(item.reservationId);
  }
  return ids;
}

/** Cards share one shape whether they come from the calendar or the account list. */
export function seriesOf(item: ReservationItem) {
  return { id: item.seriesId, title: item.title, cover: item.cover, intro: item.intro,
    totalEpisodes: item.episodeCount, tags: [], actors: [] as string[] };
}
