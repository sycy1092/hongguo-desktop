import { describe, expect, it } from 'vitest';
import type { ReservationHistoryEntry, ReservationItem, ReservationList } from '../shared/contracts';
import { dayDistance, dayLabel, historyLabels, historyState, publishLabel, reservedIds, seriesOf, seriesOfHistory, stampLabel, upcomingDays } from './reservations';

const TODAY = '20261120';
const item = (patch: Partial<ReservationItem> = {}): ReservationItem => ({
  id: '7704223871410392089', seriesId: '', reservationId: '7704223871410392089',
  title: '病弱千金，百鬼让路第二季', cover: '', intro: '', episodeCount: 55,
  publishAt: 0, note: '预计11月23日上线', reserveText: '86.5万人预约', online: false, ...patch });

describe('预约日历的日期标签', () => {
  it('今天、明天、后天和一周内的星期', () => {
    expect(dayLabel(TODAY, TODAY)).toEqual({ key: TODAY, label: '今天', sub: '11月20日' });
    expect(dayLabel('20261121', TODAY).label).toBe('明天');
    expect(dayLabel('20261122', TODAY).label).toBe('后天');
    expect(dayLabel('20261123', TODAY)).toEqual({ key: '20261123', label: '周一', sub: '11月23日' });
  });
  it('超过一周直接给日期', () => {
    expect(dayLabel('20261210', TODAY)).toEqual({ key: '20261210', label: '12月10日', sub: '2026年' });
  });
  it('非法日期原样返回，不编造星期', () => {
    expect(dayLabel('2026-11-23', TODAY)).toEqual({ key: '2026-11-23', label: '2026-11-23', sub: '' });
    expect(dayDistance('2026-11-23', TODAY)).toBeNull();
    expect(dayDistance('20261123', '')).toBeNull();
  });
  it('只保留今天及未来七天，并去掉重复和过期日期', () => {
    const days = upcomingDays(['20261113', '20261120', '20261123', '20261123', '20261130', '20261201'], TODAY);
    expect(days.map(day => day.key)).toEqual(['20261120', '20261123', '20261130', '20261201']);
    const week = ['20261120', '20261121', '20261122', '20261123', '20261124', '20261125', '20261126', '20261127', '20261128'];
    expect(upcomingDays(week, TODAY)).toHaveLength(8);
  });
});

describe('预约卡片状态', () => {
  it('优先显示红果给的预计上线文案', () => {
    expect(publishLabel(item())).toBe('预计11月23日上线');
    expect(publishLabel(item({ note: '', publishAt: 1795363560 }))).toMatch(/月\d+日上线$/);
    expect(publishLabel(item({ note: '', publishAt: 0 }))).toBe('即将上线');
    expect(publishLabel(item({ online: true, note: '已上线' }))).toBe('已上线');
  });
  it('已预约集合来自两个分区的预约标识', () => {
    const list: ReservationList = {
      upcoming: [item()], online: [item({ id: '7708340921548426265', seriesId: '7708340921548426265', reservationId: '7708340921548426265', online: true })],
      history: [], updatedAt: 0, stale: false };
    expect([...reservedIds(list)].sort()).toEqual(['7704223871410392089', '7708340921548426265']);
    expect(reservedIds(null).size).toBe(0);
  });
  it('未上线作品用预约标识作为详情占位，上线后有真实剧集号', () => {
    expect(seriesOf(item()).id).toBe('');
    expect(seriesOf(item({ seriesId: '7708340921548426265' })).id).toBe('7708340921548426265');
    expect(seriesOf(item({ episodeCount: 55 })).totalEpisodes).toBe(55);
  });
});

const entry = (patch: Partial<ReservationHistoryEntry> = {}): ReservationHistoryEntry => ({
  id: '7704223871410392089', itemId: '7704223871410392089', seriesId: '', title: '病弱千金，百鬼让路第二季',
  cover: '', episodeCount: 55, publishAt: 1795363560, reservedAt: 1795200000, cancelledAt: 0,
  online: false, seenAt: 0, ...patch });

describe('预约记录状态', () => {
  const NOW = 1795300000;
  it('预约过但还没到上线时间是待上线', () => {
    expect(historyState(entry(), NOW)).toBe('upcoming');
  });
  it('过了预计上线时间就是已上线，这条记录本机也留着', () => {
    expect(historyState(entry({ publishAt: 1795300000 }), NOW)).toBe('launched');
    expect(historyLabels.launched).toBe('已上线');
  });
  it('上游说已上线就按上游算', () => {
    expect(historyState(entry({ online: true, seenAt: NOW }), NOW)).toBe('launched');
  });
  it('上游仍标待上线的延期剧，不会被本机时间翻成已上线', () => {
    expect(historyState(entry({ publishAt: 1795000000, seenAt: NOW }), NOW)).toBe('upcoming');
  });
  it('上次看到时还没到点、之后没再读到，按已上线处理', () => {
    expect(historyState(entry({ publishAt: 1795000000, seenAt: 1794900000 }), NOW)).toBe('launched');
  });
  it('取消过的记录状态优先，不会被当成已上线', () => {
    expect(historyState(entry({ publishAt: 1795300000, cancelledAt: 1795350000 }), NOW)).toBe('cancelled');
    expect(historyLabels.cancelled).toBe('已取消');
  });
  it('没有上线时间时按待上线处理，不猜日期', () => {
    expect(historyState(entry({ publishAt: 0 }), NOW)).toBe('upcoming');
  });
  it('已上线记录可以带剧集号打开详情', () => {
    expect(seriesOfHistory(entry({ seriesId: '7708340921548426265' })).id).toBe('7708340921548426265');
    expect(seriesOfHistory(entry()).id).toBe('');
  });
  it('日期标签用本地月日，未设置返回空', () => {
    expect(stampLabel(1795363560)).toMatch(/^11月2[23]日$/);
    expect(stampLabel(0)).toBe('');
    expect(stampLabel(Number.NaN)).toBe('');
  });
  it('已上线卡片显示上线日期而不是只有“已上线”', () => {
    expect(publishLabel(item({ online: true, publishAt: 1795363560 }))).toMatch(/^11月2[23]日上线$/);
    expect(publishLabel(item({ online: true }))).toBe('已上线');
  });
});
