#!/usr/bin/env python3
"""Spekulacyjna prognoza 0.33% - NIEZALEŻNY moduł: własne pliki (data/spec033/), własny stan (spec_state.json).
Zdarzenie: od zamknięcia ostatniej świecy 1h, który poziom zostanie dotknięty pierwszy w ciągu 12 godzin:
+0,33% (wzrost) czy -0,33% (spadek). Brak dotknięcia = timeout (poza statystyką).
Model wybierany na historii (walk-forward): brak / godzina / dzień tygodnia / dzień+godzina.
Nie czyta ani nie zmienia state.json ani danych głównej prognozy."""
import os, csv, json, math, time, datetime as dt
import bot

D = os.path.join(bot.ROOT, 'data', 'spec033')
CSV = os.path.join(D, 'candles1h.csv')
PRED = os.path.join(D, 'predictions.jsonl')
RES = os.path.join(D, 'results.jsonl')
STATE = os.path.join(bot.ROOT, 'spec_state.json')
H1, W, THR = 3600, 12, 0.0033
BOOT = bot.ts(2016, 1, 1)
MODELS = ['none', 'hour', 'dow', 'dow+hour']
KG = [5, 10, 20, 50, 100, 200, 500, 1000]


def fetch_1h(start, end):
    out, s = {}, start
    while s < end:
        e = min(end, s + 299 * H1)
        rows = bot.get('https://api.exchange.coinbase.com/products/BTC-USD/candles',
                       {'granularity': H1, 'start': bot.iso(s), 'end': bot.iso(e)})
        if not isinstance(rows, list):
            raise RuntimeError('Coinbase 1h: nieoczekiwana odpowiedź')
        for t, low, high, op, cl, _v in rows:
            out[int(t)] = (float(op), float(high), float(low), float(cl))
        s = e + H1
        time.sleep(0.35)
    return out


def load_hours():
    if not os.path.exists(CSV):
        return []
    with open(CSV, newline='') as f:
        return [dict(t=int(r['t']), o=float(r['o']), h=float(r['h']), l=float(r['l']), c=float(r['c']))
                for r in csv.DictReader(f)]


def append_hours(rows):
    new = not os.path.exists(CSV)
    with open(CSV, 'a', newline='') as f:
        w = csv.writer(f)
        if new:
            w.writerow(['t', 'o', 'h', 'l', 'c'])
        for b in rows:
            w.writerow([b['t'], b['o'], b['h'], b['l'], b['c']])


def label(hs, i):
    """1 = pierwszy dotknięty +0,33%, 0 = -0,33%, None = brak dotknięcia w 12h.
    Jeśli obie granice dotknięte w tej samej świecy, rozstrzyga kierunek tej świecy."""
    ref = hs[i]['c']
    up_l, dn_l = ref * (1 + THR), ref * (1 - THR)
    for j in range(i + 1, i + W + 1):
        b = hs[j]
        hu, hd = b['h'] >= up_l, b['l'] <= dn_l
        if hu and hd:
            return int(b['c'] >= b['o'])
        if hu:
            return 1
        if hd:
            return 0
    return None


def keyof(name, t):
    d = (t // 86400 + 3) % 7  # 0 = poniedziałek (UTC)
    h = (t % 86400) // 3600
    return {'none': 0, 'hour': h, 'dow': d, 'dow+hour': d * 24 + h}[name]


def walk(labs, name, k):
    up, n, br, hit, m = {}, {}, 0.0, 0, 0
    for t, y in labs:
        kk = keyof(name, t)
        u, nn = up.get(kk, 0), n.get(kk, 0)
        p = (u + k / 2) / (nn + k)
        br += (p - y) ** 2
        hit += int((p >= .5) == bool(y))
        m += 1
        up[kk], n[kk] = u + y, nn + 1
    return dict(br=br / m, acc=hit / m, m=m, up=up, n=n)


def wilson(k, n, z=1.96):
    if n <= 0:
        return [None, None]
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    w = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return [round(c - w, 4), round(c + w, 4)]


def main():
    os.makedirs(D, exist_ok=True)
    now = int(time.time())
    hs = load_hours()
    raw = fetch_1h(hs[-1]['t'] if hs else BOOT, now)
    closed = [dict(t=t, o=v[0], h=v[1], l=v[2], c=v[3]) for t, v in sorted(raw.items()) if t + H1 <= now]
    new = [b for b in closed if not hs or b['t'] > hs[-1]['t']]
    if new:
        append_hours(new)
        hs += new
    if len(hs) < W + 200:
        raise SystemExit('za mało danych 1h')
    cur = raw.get(now - now % H1)
    px = cur[3] if cur else hs[-1]['c']

    labs = [(hs[i]['t'] + H1, lab) for i in range(len(hs) - W) for lab in [label(hs, i)] if lab is not None]
    best = None
    for name in MODELS:
        for k in KG:
            r = walk(labs, name, k)
            if best is None or r['br'] < best[2]['br']:
                best = (name, k, r)
    name, k, r = best

    # rozliczanie prognoz na żywo, tylko po zamknięciu całego okna 12h
    preds, res = bot.load_jsonl(PRED), bot.load_jsonl(RES)
    done = {x['s'] for x in res}
    idx = {b['t']: i for i, b in enumerate(hs)}
    for pr in preds:
        if pr['s'] in done or pr['s'] not in idx or idx[pr['s']] + W >= len(hs):
            continue
        y = label(hs, idx[pr['s']])
        rec = dict(s=pr['s'], p=pr['p'], y=y,
                   br=None if y is None else round((pr['p'] - y) ** 2, 6),
                   hit=None if y is None else int((pr['p'] >= .5) == bool(y)))
        bot.append_jsonl(RES, rec)
        res.append(rec)
        done.add(pr['s'])
    dec = [x for x in res if x.get('y') is not None]
    ln = len(dec)
    lbr = sum(x['br'] for x in dec) / ln if ln else None
    lacc = sum(x['hit'] for x in dec) / ln if ln else None
    fallback = ln >= 200 and lbr > .25

    s_ref, ref = hs[-1]['t'], hs[-1]['c']
    if fallback:
        r = walk(labs, 'none', 1000)
        name, k = 'none', 1000
        p, mname = .5, 'zapas: rzut monetą (model przegrywa na żywo)'
    else:
        kk = keyof(name, s_ref + H1)
        p = (r['up'].get(kk, 0) + k / 2) / (r['n'].get(kk, 0) + k)
        mname = f'{name}, k={k}'
    if s_ref not in {x['s'] for x in preds}:
        bot.append_jsonl(PRED, dict(s=s_ref, p=round(p, 4), model=mname, ref=ref, issued=now))

    eff, live_eff = r['m'] / W, ln / W
    gr = walk(labs, 'dow+hour', k)
    grid = [[round(gr['up'][d * 24 + h] / gr['n'][d * 24 + h], 3) if gr['n'].get(d * 24 + h, 0) >= 30 else None
             for h in range(24)] for d in range(7)]
    shown = hs[-72:] + ([dict(t=now - now % H1, o=cur[0], h=cur[1], l=cur[2], c=cur[3])] if cur else [])
    state = dict(
        updated=now, price=px, ref=ref, ref_time=s_ref + H1,
        levels=dict(up=round(ref * (1 + THR), 2), dn=round(ref * (1 - THR), 2)),
        model=dict(name=mname, p_up=round(p, 4), p_down=round(1 - p, 4), k=k, walk_n=r['m'],
                   walk_acc=round(r['acc'], 4), walk_brier=round(r['br'], 4), eff_n=round(eff, 1),
                   walk_ci=wilson(round(r['acc'] * eff), eff), live_n=ln,
                   live_acc=round(lacc, 4) if ln else None, live_brier=round(lbr, 4) if ln else None,
                   live_ci=wilson(round(lacc * live_eff), live_eff) if ln else [None, None], fallback=fallback),
        timeout_rate=round(1 - len(labs) / (len(hs) - W), 4),
        grid=grid,
        candles=[{x: b[x] for x in 'tohlc'} for b in shown])
    with open(STATE + '.tmp', 'w') as f:
        json.dump(state, f)
    os.replace(STATE + '.tmp', STATE)
    print('SPEC OK', mname, round(p, 4), 'cena', round(px), 'zdarzenia', len(labs), 'rozliczenia na żywo', ln)


if __name__ == '__main__':
    main()
