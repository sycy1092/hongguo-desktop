import { describe, expect, it } from 'vitest';
import { chooseStartQuality, downgrade } from './start-quality';

describe('起播画质选择', () => {
  it('按目标清晰度降一档', () => {
    expect(downgrade('auto')).toBe('720p');
    expect(downgrade('1080p')).toBe('720p');
    expect(downgrade('720p')).toBe('540p');
    expect(downgrade('540p')).toBe('540p');
  });

  it('首选画质已在本地时保持原样，并标记为命中缓存', async () => {
    const bridge = { request: async () => ({ ready: true }) };
    expect(await chooseStartQuality(bridge as never, '123', 5, 'auto')).toEqual({ quality: 'auto', cached: true });
    expect(await chooseStartQuality(bridge as never, '123', 5, '1080p')).toEqual({ quality: '1080p', cached: true });
  });

  it('首选不在本地时逐个探更低档位，最后降一档起播并标记未缓存', async () => {
    const seen: string[] = [];
    const bridge = {
      request: async (_path: string, options?: { body?: { quality?: string } }) => {
        seen.push(String(options?.body?.quality));
        return { ready: false };
      },
    };
    expect(await chooseStartQuality(bridge as never, '123', 5, 'auto')).toEqual({ quality: '720p', cached: false });
    expect(seen).toEqual(['auto', '720p', '540p']);
  });

  it('低一档已有缓存时直接用它，并且不算“未缓存”', async () => {
    const bridge = {
      request: async (_path: string, options?: { body?: { quality?: string } }) =>
        ({ ready: String(options?.body?.quality) === '720p' }),
    };
    expect(await chooseStartQuality(bridge as never, '123', 5, 'auto')).toEqual({ quality: '720p', cached: true });
  });

  it('probe 失败时按未缓存处理', async () => {
    const bridge = { request: async () => { throw new Error('offline'); } };
    expect(await chooseStartQuality(bridge as never, '123', 5, '1080p')).toEqual({ quality: '720p', cached: false });
  });
});
