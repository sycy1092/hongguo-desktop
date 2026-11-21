import { ArrowRight, BellRing, Check, LoaderCircle, RefreshCw } from 'lucide-react';
import { useCallback, useEffect, useRef, useState } from 'react';
import type { ReservationCalendar, ReservationChange, ReservationHistoryEntry, ReservationItem, ReservationList, Series } from '../../shared/contracts';
import { historyLabels, historyState, publishLabel, reservedIds, seriesOf, seriesOfHistory, stampLabel, upcomingDays } from '../reservations';
import { Empty, Failure, Loading, Poster, message } from './ui';
import './Reservations.css';

interface Props {
  loggedIn: boolean;
  uid: string;
  notify: (text: string) => void;
  onOpen: (series: Series) => void;
  onLogin: () => void;
}

const target = (item: ReservationItem) => item.reservationId;

export default function Reservations({ loggedIn, uid, notify, onOpen, onLogin }: Props) {
  const [tab, setTab] = useState<'upcoming' | 'mine'>('upcoming');
  const [calendar, setCalendar] = useState<ReservationCalendar | null>(null);
  const [loading, setLoading] = useState(true), [moreLoading, setMoreLoading] = useState(false), [error, setError] = useState('');
  const [mine, setMine] = useState<ReservationList | null>(null);
  const [mineLoading, setMineLoading] = useState(false), [mineError, setMineError] = useState('');
  const [busy, setBusy] = useState('');
  const [allHistory, setAllHistory] = useState(false);
  const generation = useRef(0);

  const load = useCallback(async (date: string, cursor = '') => {
    const id = ++generation.current;
    if (cursor) setMoreLoading(true); else { setLoading(true); setCalendar(null); }
    setError('');
    try {
      const params = new URLSearchParams();
      if (date) params.set('date', date);
      if (cursor) params.set('cursor', cursor);
      const query = params.toString();
      const value = await window.hongguo.request<ReservationCalendar>(`/reservations/upcoming${query ? `?${query}` : ''}`);
      if (id !== generation.current) return;
      setCalendar(previous => cursor && previous && previous.date === value.date
        ? { ...value, items: [...previous.items, ...value.items.filter(row => !previous.items.some(seen => seen.id === row.id))] }
        : value);
    } catch (e) { if (id === generation.current) setError(message(e)); }
    finally { if (id === generation.current) { setLoading(false); setMoreLoading(false); } }
  }, []);

  const loadMine = useCallback(async (refresh = false) => {
    if (!loggedIn) { setMine(null); setMineError(''); return; }
    setMineLoading(true); setMineError('');
    try { setMine(await window.hongguo.request<ReservationList>(`/account/reservations${refresh ? '?refresh=true' : ''}`)); }
    catch (e) { setMineError(message(e)); }
    finally { setMineLoading(false); }
  }, [loggedIn]);

  useEffect(() => { void load(''); }, [load]);
  useEffect(() => { void loadMine(); }, [loadMine, uid]);
  useEffect(() => { if (tab === 'mine') void loadMine(); }, [tab, loadMine]);

  // The server's current day lists what already launched; the first day that can
  // still be reserved is what "即将上线" should open with, once per visit.
  const advanced = useRef(false);
  useEffect(() => {
    if (!calendar || advanced.current || calendar.date !== calendar.today || !calendar.items.length) return;
    if (calendar.items.some(item => !item.online)) return;
    const next = upcomingDays(calendar.dates, calendar.today).find(day => day.key > calendar.today);
    if (!next) return;
    advanced.current = true;
    void load(next.key);
  }, [calendar, load]);

  const reserved = reservedIds(mine);
  const days = calendar ? upcomingDays(calendar.dates, calendar.today) : [];

  const toggle = async (item: ReservationItem, next: boolean) => {
    const id = target(item);
    if (!id || busy) return;
    if (!loggedIn) { notify('登录红果账号后才能预约，预约记录会同步到手机'); onLogin(); return; }
    setBusy(id);
    try {
      const result = await window.hongguo.request<ReservationChange>('/account/reservation', {
        method: 'POST', body: { itemId: id, reserved: next, expectedUid: uid } });
      if (result.synced) notify(next ? `已预约《${item.title}》，开播当天提醒你` : `已取消《${item.title}》的预约`);
      else notify(result.message || '这次预约还没有确认，刷新后核对预约列表');
      await Promise.all([load(calendar?.date || ''), loadMine(true)]);
    } catch (e) { notify(message(e)); }
    finally { setBusy(''); }
  };

  const refresh = () => { if (tab === 'mine') void loadMine(true); else void load(calendar?.date || ''); };

  const card = (item: ReservationItem) => {
    const id = target(item), saved = !!id && reserved.has(id);
    return <article className={`reserve-card ${item.online ? 'launched' : ''}`} key={item.id || id}>
      <div className="reserve-art">
        <Poster cover={item.cover} title={item.title} className="reserve-poster"/>
        <span className="reserve-when">{publishLabel(item)}</span>
      </div>
      <strong className="reserve-title" title={item.title}>{item.title}</strong>
      <p className="reserve-meta">{item.reserveText || (item.episodeCount ? `${item.episodeCount} 集` : '红果短剧')}</p>
      <div className="reserve-actions">{item.online
        ? item.seriesId ? <button className="btn secondary" onClick={() => onOpen(seriesOf(item))}>查看详情<ArrowRight size={15}/></button>
          : <span className="reserve-hint">已上线</span>
        : id ? <button className={`btn ${saved ? 'secondary' : 'primary'}`} aria-pressed={saved} disabled={busy === id}
            onClick={() => void toggle(item, !saved)}>
            {busy === id ? <LoaderCircle className="spin" size={15}/> : saved ? <Check size={15}/> : <BellRing size={15}/>}
            {saved ? '已预约' : '预约'}
          </button> : <span className="reserve-hint">即将上线</span>}
      </div>
    </article>;
  };

  const row = (item: ReservationItem) => {
    const id = target(item);
    return <div className="reserve-row" key={`${item.id}:${id}`}>
      <Poster cover={item.cover} title={item.title} className="reserve-thumb"/>
      <div className="reserve-row-copy">
        <strong title={item.title}>{item.title}</strong>
        <small>{publishLabel(item)}{item.reserveText ? ` · ${item.reserveText}` : ''}{item.episodeCount ? ` · ${item.episodeCount} 集` : ''}{item.source === 'local' ? ' · 本机记录' : ''}</small>
      </div>
      <div className="reserve-row-actions">{item.online && item.seriesId &&
        <button className="btn subtle" onClick={() => onOpen(seriesOf(item))}>查看详情<ArrowRight size={15}/></button>}
        {!item.online && id && <button className="btn secondary" disabled={busy === id} onClick={() => void toggle(item, false)}>
          {busy === id ? <LoaderCircle className="spin" size={15}/> : null}取消预约</button>}
      </div>
    </div>;
  };

  const historyRow = (entry: ReservationHistoryEntry) => {
    const state = historyState(entry, Math.floor(Date.now() / 1000));
    const when = entry.cancelledAt > 0 ? ` · 取消于 ${stampLabel(entry.cancelledAt)}`
      : entry.publishAt > 0 ? state === 'launched' ? ` · ${stampLabel(entry.publishAt)}上线` : ` · 预计 ${stampLabel(entry.publishAt)}上线` : '';
    return <div className="reserve-row" key={`history:${entry.id}`}>
      <Poster cover={entry.cover} title={entry.title} className="reserve-thumb"/>
      <div className="reserve-row-copy">
        <strong title={entry.title}>{entry.title}</strong>
        <small><span className={`reserve-state ${state}`}>{historyLabels[state]}</span>
          {entry.reservedAt > 0 ? ` 预约于 ${stampLabel(entry.reservedAt)}` : ' 本机未记录预约时间'}{when}{entry.episodeCount ? ` · ${entry.episodeCount} 集` : ''}</small>
      </div>
      {entry.seriesId && <div className="reserve-row-actions">
        <button className="btn subtle" onClick={() => onOpen(seriesOfHistory(entry))}>查看详情<ArrowRight size={15}/></button>
      </div>}
    </div>;
  };

  const section = (title: string, rows: ReservationItem[], empty: string) => <section className="reserve-section">
    <div className="section-heading"><h2>{title}</h2><span>{rows.length} 部作品</span></div>
    {rows.length ? <div className="reserve-rows">{rows.map(row)}</div> : <p className="reserve-empty">{empty}</p>}
  </section>;

  return <div className="reservations-page library-page">
    <div className="page-heading">
      <div><h1>预约上线</h1><p>即将开播的剧集先预约，上线当天在红果提醒你；已预约会与手机同步。</p></div>
      <button className="btn secondary" onClick={refresh} disabled={tab === 'mine' ? mineLoading : loading}>
        <RefreshCw size={16} className={(tab === 'mine' ? mineLoading : loading) ? 'spin' : ''}/>刷新
      </button>
    </div>
    <div className="reserve-tabs" role="tablist" aria-label="预约">
      <button role="tab" aria-selected={tab === 'upcoming'} className={tab === 'upcoming' ? 'active' : ''} onClick={() => setTab('upcoming')}>即将上线</button>
      <button role="tab" aria-selected={tab === 'mine'} className={tab === 'mine' ? 'active' : ''} onClick={() => setTab('mine')}>
        已预约{loggedIn && mine ? <em>{mine.upcoming.length + mine.online.length}</em> : null}
      </button>
    </div>

    {tab === 'upcoming' ? <>
      {loading && !calendar ? <Loading text="正在读取上线日历…"/>
        : error && !calendar ? <Failure text={error} retry={() => void load('')}/>
        : calendar ? <>
          <div className="reserve-days" role="tablist" aria-label="开播日期">{days.map(day =>
            <button key={day.key} role="tab" aria-selected={!error && day.key === calendar.date}
              className={!error && day.key === calendar.date ? 'active' : ''} onClick={() => void load(day.key)}>
              <strong>{day.label}</strong><small>{day.sub}</small></button>)}</div>
          {error && <div className="reserve-warning" role="status"><span>{error}</span><button className="btn subtle" onClick={() => void load(calendar.date)}>重试</button></div>}
          {calendar.items.length ? <div className="reserve-grid">{calendar.items.map(card)}</div>
            : <Empty title="这一天还没有可预约的剧集" text="换一个日期看看，或者稍后刷新上线日历。"/>}
          {calendar.hasMore && calendar.items.length > 0 && <div className="load-more">
            <button className="btn secondary" disabled={moreLoading} onClick={() => void load(calendar.date, calendar.cursor)}>
              {moreLoading ? '正在加载…' : '加载更多'}<ArrowRight size={16}/></button></div>}
        </> : null}
    </> : !loggedIn
      ? <Empty title="登录后查看已预约" text="预约与开播记录跟红果账号走，登录后与手机同步，并在这台电脑留一份记录。">
          <button className="btn primary" onClick={onLogin}>去登录<ArrowRight size={16}/></button></Empty>
      : mineLoading && !mine ? <Loading text="正在读取你的预约…"/>
      : mineError && !mine ? <Failure text={mineError} retry={() => void loadMine(true)}/>
      : <>
        {mine?.warning && <div className="reserve-warning" role="status"><span>{mine.warning}</span></div>}
        {mineError && mine && <div className="reserve-warning" role="status"><span>已保留上次的预约列表。{mineError}</span></div>}
        {section('待上线', mine?.upcoming || [], '还没有待上线的预约。在上线日历里挑一部剧预约吧。')}
        {section('已上线', mine?.online || [], '预约过的剧上线后会出现在这里；上游不再返回时，本机记录也会保留。')}
        {!!mine?.history.length && <section className="reserve-section">
          <div className="section-heading"><h2>预约记录</h2><span>{mine.history.length} 条 · 本机保存</span></div>
          <div className="reserve-rows">{(allHistory ? mine.history : mine.history.slice(0, 8)).map(historyRow)}</div>
          {!allHistory && mine.history.length > 8 && <div className="load-more">
            <button className="btn secondary" onClick={() => setAllHistory(true)}>显示全部记录<ArrowRight size={16}/></button></div>}
        </section>}
      </>}
  </div>;
}
