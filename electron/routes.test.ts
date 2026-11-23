import { describe, expect, it } from 'vitest';
import { allowedRoute } from './routes';

const accepted = [
  '/health',
  '/catalog/home?genre=short_play',
  '/catalog/search?q=%E7%9F%AD%E5%89%A7&cursor=abc',
  '/catalog/search/suggestions?query=ab',
  '/catalog/rank?board=hot&genre=short_play',
  '/catalog/browse?genre=short_play&sort=hot_score',
  '/catalog/filters?genre=short_play',
  '/catalog/comments?seriesId=12345678&episode=1&cursor=0',
  '/catalog/danmaku?seriesId=12345678&episode=1&position=0&duration=60',
  '/catalog/series/12345678',
  '/catalog/series/12345678/next-season?refresh=true',
  '/catalog/series/12345678/seasons',
  '/reservations/upcoming',
  '/reservations/upcoming?date=20261123&cursor=24',
  '/account/session',
  '/account/reservations',
  '/account/reservations?refresh=true',
  '/account/reservation',
  '/account/favorites',
  '/account/favorite',
  '/account/history?cursor=&limit=100',
  '/account/qr',
  '/account/qr/0123456789abcdef0123456789abcdef',
  '/account/mfa/verify',
  '/media/session/abc_DEF-123',
  '/media/cache',
  '/media/cache/clear',
  '/media/cached',
  '/media/prefetch',
];

const rejected = [
  '/account/reservation/extra',
  '/account/password',
  '/reservations',
  '/reservations/upcoming/extra',
  '/media/session/../../etc/passwd',
  '/media/session/abc/index.m3u8',
  'https://example.invalid/account/session',
  '//account/session',
  '/account/session#fragment',
  '/account/session\r\nX-Injected: 1',
  '/health?x=1#frag',
  '',
  '/',
];

describe('主进程接口白名单', () => {
  it('放行界面实际使用的路由', () => {
    for (const route of accepted) expect(allowedRoute(route), route).toBe(true);
  });
  it('拒绝白名单以外的路径和带换行的请求', () => {
    for (const route of rejected) expect(allowedRoute(route), JSON.stringify(route)).toBe(false);
  });
  it('拒绝非字符串和过长的路由', () => {
    expect(allowedRoute(undefined)).toBe(false);
    expect(allowedRoute(null)).toBe(false);
    expect(allowedRoute(42)).toBe(false);
    expect(allowedRoute('/health?' + 'a'.repeat(4000))).toBe(false);
  });
});
