import { describe, expect, it } from 'vitest';
import { loadWatched, markWatched, parseWatched, watchedKey } from './watched';

const memory = () => {
  const data = new Map<string, string>();
  return {
    getItem: (key: string) => data.get(key) ?? null,
    setItem: (key: string, value: string) => void data.set(key, value),
    data,
  };
};

describe('已播放记录', () => {
  it('解析时去掉重复与非法值并排序', () => {
    expect(parseWatched('["3",1,2,2,0,-5,999999]')).toEqual([1, 2]);
    expect(parseWatched('')).toEqual([]);
    expect(parseWatched('not json')).toEqual([]);
  });

  it('写入后能按剧集读回', () => {
    const storage = memory();
    const first = markWatched('123', 7, [], storage);
    expect(first).toEqual([7]);
    const second = markWatched('123', 5, first, storage);
    expect(second).toEqual([5, 7]);
    expect(loadWatched('123', storage)).toEqual([5, 7]);
    expect(storage.data.get(watchedKey('123'))).toBe('[5,7]');
    expect(loadWatched('456', storage)).toEqual([]);
  });

  it('存储不可用时仍然返回内存结果', () => {
    const storage = { getItem: () => { throw new Error('denied'); }, setItem: () => { throw new Error('denied'); } };
    expect(loadWatched('123', storage as never)).toEqual([]);
    expect(markWatched('123', 9, [1], storage as never)).toEqual([1, 9]);
  });
});
