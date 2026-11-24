import { describe, expect, it } from 'vitest';
import { chooseStartQuality, downgrade } from './start-quality';

describe('起播画质选择', () => {
  it('按目标清晰度降一档', () => {
    expect(downgrade('auto')).toBe('720p');
    expect(downgrade('1080p')).toBe('720p');
    expect(downgrade('720p')).toBe('540p');
    expect(downgrade('540p')).toBe('540p');
  });

  it('首选画质已在本地时保持原样', async () => {
    const bridge = { request: async () => ({ ready: true }) };
    expect(await chooseStartQuality(bridge as never, '123', 5, 'auto')).toBe('auto');
    expect(await chooseStartQuality(bridge as never, '123', 5, '1080p')).toBe('1080p');
  });

  it('首选不在本地时降一档，并用 probe 询问', async () => {
    const seen: string[] = [];
    const bridge = {
      request: async (_path: string, options?: { body?: { quality?: string } }) => {
        seen.push(String(options?.body?.quality));
        return { ready: false };
      },
    };
    expect(await chooseStartQuality(bridge as never, '123', 5, 'auto')).toBe('720p');
    expect(seen).toEqual(['auto']);
  });

  it('probe 失败时也返回降档结果', async () => {
    const bridge = { request: async () => { throw new Error('offline'); } };
    expect(await chooseStartQuality(bridge as never, '123', 5, '1080p')).toBe('720p');
  });
});
