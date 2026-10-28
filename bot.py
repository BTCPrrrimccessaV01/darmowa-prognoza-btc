#!/usr/bin/env python3
"""Darmowa Prognoza BTC - bot (uruchamiany przez GitHub Actions co ~15 min, za darmo).
Źródła bez kluczy API: Coinbase Exchange (świece 6h -> składane do 12h, historia od 2015),
mempool.space (onchain, portfele). Opcjonalnie Telegram (alerty w tle, bez otwartej przeglądarki).
Zasada: pliki w data/ są TYLKO dopisywane. Pełna historia zmian jest w Git."""
import os, json, csv, math, time, statistics, datetime as dt, urllib.request, urllib.parse

ROOT = os.environ.get('BOT_ROOT', os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, 'data')
F = {k: os.path.join(DATA, v) for k, v in dict(
    csv='candles12h.csv', pred='predictions.jsonl', res='results.jsonl',
    onc='onchain.jsonl', wal='wallets.jsonl', meta='meta.json').items()}
STATE = os.path.join(ROOT, 'state.json')
H12, H6, DAY = 43200, 21600, 86400


def ts(y, m, d):
    return int(dt.datetime(y, m, d, tzinfo=dt.timezone.utc).timestamp())


HAL = [ts(2012, 11, 28), ts(2016, 7, 9), ts(2020, 5, 11), ts(2024, 4, 20)]
BOOT = ts(2015, 1, 1)
WAL = ['143gLvWYUojXaWZRrxquRKpVNTkhmr415B', 'bc1ql49ydapnjafl5t2cp9zqpjwe6pdgmxy98859v2',
       '34xp4vRoCGJym3xR7yCVPFHoCNxv4Twseo', '1F3Cpgben5uRAMptnPRL9coAbKp9YmWqfb',
       'bc1qhtvsrdu6a8jddqjnudugvzhqwdg8kdyjf2yfl6', 'bc1qumvs45e69rvfd9vqknzyz9wg0xzvnhmx6mt3cc',
       'bc1qx76pl3zzunj045tl0dhx36j2gpmw3mxt57l5un', 'bc1qkrr502g34cy5yusmurnzksc3elcxyrlh9znpudp0rzt3j02wvc6q9tt8ce',
       'bc1q88zfnu6wjqqpxyaksmc3mcgakwaqt7z68tkw0jx87gdn25fhfkuqy23psm',
       'bc1pdwu79dady576y3fupmm82m3g7p2p9f6hgyeqy0tdg7ztxg7xrayqlkl8j9']
MODELS = ['none', 'cycle', 'momentum', 'cycle+momentum']
KG = [5, 10, 20, 50, 100, 200, 500, 1000]


def get(url, params=None, text=False):
    if params:
        url += '?' + urllib.parse.urlencode(params)
    err = None
    for i in range(3):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'darmowa-prognoza-btc/1.0'})
            with urllib.request.urlopen(req, timeout=25) as r:
                body = r.read().decode()
            return body if text else json.loads(body)
        except Exception as e:
            err = e
            time.sleep(2 * (i + 1))
    raise RuntimeError(f'{urllib.parse.urlsplit(url).netloc}: {type(err).__name__}')


def iso(s):
    return dt.datetime.fromtimestamp(s, dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def coinbase_6h(start, end):
    out, s = {}, start
    while s < end:
        e = min(end, s + 299 * H6)
        rows = get('https://api.exchange.coinbase.com/products/BTC-USD/candles',
                   {'granularity': H6, 'start': iso(s), 'end': iso(e)})
        if not isinstance(rows, list):
            raise RuntimeError('Coinbase: nieoczekiwana odpowiedź')
        for t, low, high, op, cl, _v in rows:
            out[int(t)] = (float(op), float(high), float(low), float(cl))
        s = e + H6
        time.sleep(0.35)
    return out


def to12h(c6):
    blocks = {}
    for t in sorted(c6):
        o, h, l, c = c6[t]
        b = t - t % H12
        if b not in blocks:
            blocks[b] = dict(t=b, o=o, h=h, l=l, c=c, n=1)
        else:
            B = blocks[b]
            B['h'], B['l'], B['c'], B['n'] = max(B['h'], h), min(B['l'], l), c, B['n'] + 1
    return [blocks[k] for k in sorted(blocks)]


def load_csv(p):
    if not os.path.exists(p):
        return []
    with open(p, newline='') as f:
        return [dict(t=int(r['t']), o=float(r['o']), h=float(r['h']), l=float(r['l']),
                     c=float(r['c']), n=int(r['n'])) for r in csv.DictReader(f)]


def append_csv(p, rows):
    new = not os.path.exists(p)
    with open(p, 'a', newline='') as f:
        w = csv.writer(f)
        if new:
            w.writerow(['t', 'o', 'h', 'l', 'c', 'n'])
        for b in rows:
            w.writerow([b['t'], b['o'], b['h'], b['l'], b['c'], b['n']])


def load_jsonl(p):
    if not os.path.exists(p):
        return []
    with open(p) as f:
        return [json.loads(x) for x in f if x.strip()]


def append_jsonl(p, row):
    with open(p, 'a') as f:
        f.write(json.dumps(row) + '\n')


def bucket(t):
    """Faza 4-letniego cyklu (od halvingu): 8 kubełków po ~6 miesięcy."""
    h = HAL[0]
    for x in HAL:
        if x <= t:
            h = x
    return min(7, int((t - h) / DAY / 1461 * 8))


def keyof(name, cyc, mom):
    return {'none': 0, 'cycle': cyc, 'momentum': mom, 'cycle+momentum': cyc * 2 + mom}[name]


def walk(cs, name, k):
    """Walk-forward: każda świeca jest prognozowana wyłącznie na danych sprzed niej."""
    up, n, br, hit, m = {}, {}, 0.0, 0, 0
    for j in range(15, len(cs)):
        kk = keyof(name, bucket(cs[j]['t']), int(cs[j - 1]['c'] > cs[j - 15]['c']))
        u, nn = up.get(kk, 0), n.get(kk, 0)
        p = (u + k / 2) / (nn + k)
        y = int(cs[j]['c'] > cs[j]['o'])
        br += (p - y) ** 2
        hit += int((p >= .5) == bool(y))
        m += 1
        up[kk], n[kk] = u + y, nn + 1
    return dict(br=br / m, acc=hit / m, up=up, n=n)


def select(cs):
    """Bot sam wybiera model i parametr o najlepszym wyniku (Brier) na historii."""
    best = None
    for name in MODELS:
        for k in KG:
            r = walk(cs, name, k)
            if best is None or r['br'] < best[2]['br']:
                best = (name, k, r)
    return best


def keynow(name, cs):
    return keyof(name, bucket(cs[-1]['t'] + H12), int(cs[-1]['c'] > cs[-15]['c']))


def q(a, p):
    s = sorted(a)
    return s[int(p * (len(s) - 1))]


def bands(cs, p):
    cl = [b['c'] for b in cs]
    lr = [math.log(cl[i + 1] / cl[i]) for i in range(len(cl) - 1)]
    rms = lambda v: math.sqrt(sum(x * x for x in v) / len(v))
    sc = min(2, max(.5, rms(lr[-30:]) / rms(lr)))
    out = {}
    for h in (1, 2, 14):
        f = [math.log(cl[i + h] / cl[i]) for i in range(len(cl) - h)]
        drift = (p - .5) * 2 * statistics.median([abs(x) for x in f])
        out[h] = dict(lo=drift + q(f, .05) * sc, mid=drift, hi=drift + q(f, .95) * sc)
    return out


def alerts(cs, cur, px, p, bd):
    A = []
    rg = sorted((b['h'] - b['l']) / b['o'] for b in cs[-200:])
    med = rg[len(rg) // 2]
    cr = (cur['h'] - cur['l']) / cur['o'] if cur else 0
    if cr > 2.5 * med:
        A.append(f'⚡ Duża zmienność: zakres świecy {cr * 100:.1f}% (norma ~{med * 100:.1f}%)')
    if p >= .6 or p <= .4:
        A.append(f'🎯 Silna przewaga: {p * 100:.0f}% {"wzrostu" if p > .5 else "spadku"} w 12h')
    for side, v in (('górnej', px * math.exp(bd[2]['hi'])), ('dolnej', px * math.exp(bd[2]['lo']))):
        if abs(px - v) / px < .005:
            A.append(f'🎯 Cena przy {side} strefie 1d: {v:,.0f}')
    return A


def telegram(msg):
    tok, chat = os.environ.get('TG_TOKEN'), os.environ.get('TG_CHAT')
    if not (tok and chat):
        return
    try:
        get(f'https://api.telegram.org/bot{tok}/sendMessage', {'chat_id': chat, 'text': msg}, text=True)
    except Exception as e:
        print('Telegram:', type(e).__name__)


def onchain():
    h = int(get('https://mempool.space/api/blocks/tip/height', text=True).strip())
    f = get('https://mempool.space/api/v1/fees/recommended')
    d = get('https://mempool.space/api/v1/difficulty-adjustment')
    return dict(height=h, fast_fee=f['fastestFee'], diff_change=round(d['difficultyChange'], 2),
                remaining=d['remainingBlocks'])


def wallets_now():
    cur = {}
    for a in WAL:
        try:
            c = get(f'https://mempool.space/api/address/{a}')['chain_stats']
            cur[a] = dict(tx=c['tx_count'], bal=round((c['funded_txo_sum'] - c['spent_txo_sum']) / 1e8, 8))
        except Exception as e:
            print('portfel', a[:10], type(e).__name__)
        time.sleep(0.2)
    return cur


def wallet_rows(cur, now):
    log = load_jsonl(F['wal'])
    last, base = {}, {}
    for x in log:
        last[x['a']] = x
        if x['t'] <= now - DAY:
            base[x['a']] = x
    for a, v in cur.items():
        if a not in last or last[a]['tx'] != v['tx']:
            append_jsonl(F['wal'], dict(t=now, a=a, tx=v['tx'], bal=v['bal']))
    out = []
    for a in WAL:
        v = cur.get(a)
        if v is None:
            out.append(dict(a=a, tx=None, bal=None, delta=0))
        else:
            out.append(dict(a=a, tx=v['tx'], bal=v['bal'], delta=v['tx'] - base[a]['tx'] if a in base else 0))
    return out


def cycle_info(cs, now):
    w = cs[-730:]
    mi = min(range(len(w)), key=lambda i: w[i]['l'])
    return dict(days=int((now - HAL[-1]) // DAY), of=1461, min2y=w[mi]['l'], days_since_min=int((len(w) - 1 - mi) / 2))


def safe(fn, default):
    try:
        return fn()
    except Exception as e:
        print('UWAGA:', type(e).__name__, e)
        return default


def main():
    os.makedirs(DATA, exist_ok=True)
    now = int(time.time())
    cs = load_csv(F['csv'])
    last_t = cs[-1]['t'] if cs else -1
    fresh = to12h(coinbase_6h(cs[-1]['t'] if cs else BOOT, now))
    new = [b for b in fresh if b['t'] + H12 <= now and b['t'] > last_t]
    if new:
        append_csv(F['csv'], new)
        cs += new
    if not cs:
        raise SystemExit('Brak danych świecowych')
    cur = next((b for b in fresh if b['t'] + H12 > now), None)
    px = cur['c'] if cur else cs[-1]['c']
    nxt = cs[-1]['t'] + H12

    # rozliczanie prognoz (samouczenie na żywo)
    preds, res = load_jsonl(F['pred']), load_jsonl(F['res'])
    done, cmap = {r['s'] for r in res}, {b['t']: b for b in cs}
    for pr in preds:
        if pr['s'] in done or pr['s'] not in cmap:
            continue
        b = cmap[pr['s']]
        up = int(b['c'] > b['o'])
        r = dict(s=pr['s'], p=pr['p'], up=up, br=round((pr['p'] - up) ** 2, 6), hit=int((pr['p'] >= .5) == bool(up)))
        append_jsonl(F['res'], r)
        res.append(r)
        done.add(pr['s'])

    name, k, r = select(cs)
    kk = keynow(name, cs)
    p = (r['up'].get(kk, 0) + k / 2) / (r['n'].get(kk, 0) + k)
    mname = f'{name}, k={k}'
    ln = len(res)
    lbr = sum(x['br'] for x in res) / ln if ln else None
    lacc = sum(x['hit'] for x in res) / ln if ln else None
    if ln >= 50 and lbr > .25:  # model przegrywa z rzutem monetą na żywo -> zapas
        p, mname = .5, 'zapas: rzut monetą (model przegrywa na żywo)'
        r = walk(cs, 'none', 1000)  # raportowana trafność musi dotyczyć użytego modelu
    if nxt not in {x['s'] for x in preds}:
        append_jsonl(F['pred'], dict(s=nxt, p=round(p, 4), model=mname, px=px, issued=now))

    onc = safe(onchain, None)
    if onc:
        lo = load_jsonl(F['onc'])
        if not lo or lo[-1]['height'] != onc['height']:
            append_jsonl(F['onc'], dict(t=now, **onc))
    wl = wallet_rows(safe(wallets_now, {}), now)

    bd = bands(cs, p)
    A = alerts(cs, cur, px, p, bd)
    meta = json.load(open(F['meta'])) if os.path.exists(F['meta']) else {}
    sig = '|'.join(a.split(':')[0] for a in A)
    if sig and sig != meta.get('last_alert'):
        telegram('Darmowa Prognoza BTC\n' + '\n'.join(A))
    meta['last_alert'] = sig
    with open(F['meta'], 'w') as f:
        json.dump(meta, f)

    shown = cs[-150:] + ([cur] if cur else [])
    state = dict(
        updated=now, price=px, n_candles=len(cs),
        candles=[{x: b[x] for x in 'tohlc'} for b in shown],
        ghost=dict(o=px, c=px * math.exp(bd[1]['mid']), h=px * math.exp(bd[1]['hi']), l=px * math.exp(bd[1]['lo'])),
        bands={nm: {x: px * math.exp(bd[h][x]) for x in ('lo', 'mid', 'hi')} for h, nm in ((1, '12h'), (2, '1d'), (14, '7d'))},
        model=dict(name=mname, p_up=round(p, 4), walk_acc=round(r['acc'], 4), walk_brier=round(r['br'], 4),
                   live_n=ln, live_acc=round(lacc, 4) if ln else None, live_brier=round(lbr, 4) if ln else None),
        alerts=A, onchain=onc, wallets=wl, cycle=cycle_info(cs, now))
    with open(STATE + '.tmp', 'w') as f:
        json.dump(state, f)
    os.replace(STATE + '.tmp', STATE)
    print('OK', round(px), mname, round(p, 4), 'nowe świece:', len(new), 'rozliczenia na żywo:', ln)


if __name__ == '__main__':
    main()
    try:
        import tf
        tf.main()
    except Exception as e:
        print('TF UWAGA:', type(e).__name__, e)
