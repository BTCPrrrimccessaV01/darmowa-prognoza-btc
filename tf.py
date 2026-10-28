#!/usr/bin/env python3
"""Wykresy interwałów 5m, 15m, 1h, 4h z prognozą (zakładka Prognoza) oraz analiza aktywności
10 portfeli na tych samych świecach (zakładka Portfelowe kombo). Osobny model i osobne pliki.
Uruchamiane przez bot.py po zapisie stanu głównego. Wynik: data/tf_state.json."""
import os, csv, json, math, time, bisect
import bot

D = os.path.join(bot.DATA, 'tf')
OUT = os.path.join(bot.DATA, 'tf_state.json')
WTX = os.path.join(D, 'wtx.jsonl')
GR = {'5m': 300, '15m': 900, '1h': 3600, '4h': 14400}
HIST = {'5m': 180 * 86400, '15m': 365 * 86400, '1h': None}
H = 6  # horyzont scenariusza w świecach
MODELS = ['none', 'hour', 'dow', 'dow+hour']
KG = [5, 10, 20, 50, 100, 200, 500, 1000]


def fetch(g, start, end):
    out, s = {}, start
    while s < end:
        e = min(end, s + 299 * g)
        rows = bot.get('https://api.exchange.coinbase.com/products/BTC-USD/candles',
                       {'granularity': g, 'start': bot.iso(s), 'end': bot.iso(e)})
        if not isinstance(rows, list):
            raise RuntimeError('Coinbase: nieoczekiwana odpowiedź')
        for t, low, high, op, cl, _v in rows:
            out[int(t)] = (float(op), float(high), float(low), float(cl))
        s = e + g
        time.sleep(0.35)
    return out


def load(p):
    if not os.path.exists(p):
        return []
    with open(p, newline='') as f:
        return [dict(t=int(r['t']), o=float(r['o']), h=float(r['h']), l=float(r['l']), c=float(r['c']))
                for r in csv.DictReader(f)]


def append(p, rows):
    new = not os.path.exists(p)
    with open(p, 'a', newline='') as f:
        w = csv.writer(f)
        if new:
            w.writerow(['t', 'o', 'h', 'l', 'c'])
        for b in rows:
            w.writerow([b['t'], b['o'], b['h'], b['l'], b['c']])


def update(tf, now):
    """Dopisuje tylko nowe zamknięte świece; pierwsze uruchomienie pobiera historię."""
    p = os.path.join(D, f'{tf}.csv')
    cs = load(p)
    g = GR[tf]
    start = cs[-1]['t'] if cs else (now - HIST[tf] if HIST[tf] else bot.ts(2016, 1, 1))
    raw = fetch(g, start, now)
    new = [dict(t=t, o=v[0], h=v[1], l=v[2], c=v[3]) for t, v in sorted(raw.items())
           if t + g <= now and (not cs or t > cs[-1]['t'])]
    if new:
        append(p, new)
        cs += new
    return cs


def agg4h(cs):
    """4h składane z 1h; tylko kompletne bloki (4 świece), równo od 00:00 UTC."""
    b = {}
    for c in cs:
        k = c['t'] - c['t'] % 14400
        if k not in b:
            b[k] = dict(t=k, o=c['o'], h=c['h'], l=c['l'], c=c['c'], n=1)
        else:
            B = b[k]
            B['h'], B['l'], B['c'], B['n'] = max(B['h'], c['h']), min(B['l'], c['l']), c['c'], B['n'] + 1
    return [v for k, v in sorted(b.items()) if v['n'] == 4]


def keyof(name, t):
    d = (t // 86400 + 3) % 7  # 0 = poniedziałek (UTC)
    h = (t % 86400) // 3600
    return {'none': 0, 'hour': h, 'dow': d, 'dow+hour': d * 24 + h}[name]


def walk(pairs, k):
    """Walk-forward: każda świeca prognozowana wyłącznie na danych sprzed niej."""
    up, n, br, hit = {}, {}, 0.0, 0
    for kk, y in pairs:
        u, nn = up.get(kk, 0), n.get(kk, 0)
        p = (u + k / 2) / (nn + k)
        br += (p - y) ** 2
        hit += int((p >= .5) == bool(y))
        up[kk], n[kk] = u + y, nn + 1
    m = len(pairs)
    return dict(br=br / m, acc=hit / m, m=m, up=up, n=n)


def wilson(k, n, z=1.96):
    if n <= 0:
        return [None, None]
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    w = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return [round(c - w, 4), round(c + w, 4)]


def verdict(ci):
    if ci[0] is None:
        return 'za mało danych'
    if ci[0] > .5:
        return 'przewaga w historii: wzrost (przedział powyżej 50%)'
    if ci[1] < .5:
        return 'przewaga w historii: spadek (przedział poniżej 50%)'
    return 'brak przewagi: przedział obejmuje 50%'


def scen(cs):
    """Granice 90% zmiany ceny po H świecach z historii danego interwału."""
    cl = [c['c'] for c in cs]
    f = sorted(math.log(cl[i + H] / cl[i]) for i in range(len(cl) - H))
    px = cl[-1]
    return px * math.exp(f[int(.05 * (len(f) - 1))]), px * math.exp(f[int(.95 * (len(f) - 1))])


def tf_model(cs, g):
    ys = [int(c['c'] > c['o']) for c in cs]
    best = None
    for name in MODELS:
        pairs = [(keyof(name, c['t']), y) for c, y in zip(cs, ys)]
        for k in KG:
            r = walk(pairs, k)
            if best is None or r['br'] < best[3]['br']:
                best = (name, k, pairs, r)
    name, k, _, r = best
    kn = keyof(name, cs[-1]['t'] + g)
    p = (r['up'].get(kn, 0) + k / 2) / (r['n'].get(kn, 0) + k)
    return p, name, k, r


def pack(cs, p, name, k, r, extra=None):
    dn, up = scen(cs)
    ci = wilson(round(r['acc'] * r['m']), r['m'])
    d = dict(model=f'{name}, k={k}', p_up=round(p, 4), walk_acc=round(r['acc'], 4), ci=ci,
             verdict=verdict(ci), n=len(cs), px=cs[-1]['c'], up_end=round(up, 2), dn_end=round(dn, 2), h=H,
             candles=[{x: c[x] for x in 'tohlc'} for c in cs[-60:]])
    if extra:
        d.update(extra)
    return d


def counts(cs, g, times):
    ts = sorted(times)
    return [bisect.bisect_left(ts, c['t'] + g) - bisect.bisect_left(ts, c['t']) for c in cs]


def spk(cnt, j):
    """Skok aktywności: liczba transakcji w świecy j co najmniej 2x średnia z 50 poprzednich."""
    return int(cnt[j] >= 2 * max(1, sum(cnt[j - 50:j]) / 50))


def wallet_model(cs, cnt):
    ys = [int(c['c'] > c['o']) for c in cs]
    best = None
    for name in ('none', 'spike'):
        pairs = [(0 if name == 'none' else spk(cnt, j - 1), ys[j]) for j in range(51, len(cs))]
        for k in KG:
            r = walk(pairs, k)
            if best is None or r['br'] < best[2]['br']:
                best = (name, k, r)
    name, k, r = best
    kn = 0 if name == 'none' else spk(cnt, len(cs) - 1)
    p = (r['up'].get(kn, 0) + k / 2) / (r['n'].get(kn, 0) + k)
    return p, name, k, r, kn


def wallet_times(now):
    """Potwierdzone transakcje 10 portfeli (czas bloku). Pierwszy bieg: do 1000 ostatnich na portfel."""
    rows = bot.load_jsonl(WTX)
    wm = {}
    for x in rows:
        wm[x['a']] = max(wm.get(x['a'], 0), x['t'])
    for a in bot.WAL:
        try:
            new, last = [], None
            for _ in range(40):
                url = f'https://mempool.space/api/address/{a}/txs' + (f'/chain/{last}' if last else '')
                page = bot.get(url)
                if not isinstance(page, list) or not page:
                    break
                stop = False
                for r in page:
                    st = r.get('status', {})
                    if not st.get('confirmed') or st.get('block_time') is None:
                        continue
                    if st['block_time'] <= wm.get(a, 0):
                        stop = True
                        break
                    new.append(st['block_time'])
                if stop:
                    break
                last = page[-1]['txid']
                time.sleep(0.2)
            for t in new:
                bot.append_jsonl(WTX, dict(a=a, t=t))
                rows.append(dict(a=a, t=t))
        except Exception as e:
            print('portfel', a[:10], type(e).__name__)
    return [x['t'] for x in rows]


def main():
    os.makedirs(D, exist_ok=True)
    now = int(time.time())
    cs_map = {}
    for tf in ('1h', '5m', '15m'):
        try:
            cs_map[tf] = update(tf, now)
        except Exception as e:
            print('TF', tf, 'błąd:', type(e).__name__, e)
    if '1h' in cs_map:
        cs_map['4h'] = agg4h(cs_map['1h'])
    wt = wallet_times(now)
    out = dict(updated=now, tf={}, wallet={})
    for tf, cs in cs_map.items():
        if len(cs) < 300:
            continue
        p, name, k, r = tf_model(cs, GR[tf])[:4]
        out['tf'][tf] = pack(cs, p, name, k, r)
        ws = [c for c in cs if wt and c['t'] >= min(wt)]
        if len(ws) >= 300:
            cnt = counts(ws, GR[tf], wt)
            p, name, k, r, kn = wallet_model(ws, cnt)
            out['wallet'][tf] = pack(ws, p, name, k, r, dict(spike_now=kn, tx_last60=sum(cnt[-60:])))
    tmp = OUT + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(out, f)
    os.replace(tmp, OUT)
    print('TF OK', {t: v['model'] for t, v in out['tf'].items()}, 'portfele:', list(out['wallet']),
          'transakcje:', len(wt))


if __name__ == '__main__':
    main()
