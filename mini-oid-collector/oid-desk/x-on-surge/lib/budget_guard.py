#!/usr/bin/env python3
"""Reference budget guard for x_on_surge (X Summarizer v0.4). Pure logic, no network. Every X request goes through precheck()
BEFORE it is sent, using the worst-case cost, so with the assumed prices spend can't pass either cap. After the call, record() adds the
actual estimate (fetch_log.est_cost_usd = n_posts*0.005 + n_users*0.010)."""
import json, os
H=os.path.dirname(os.path.abspath(__file__)); CFG=json.load(open(H+'/x-on-surge-config.json'))
P=CFG['pricing_assumption']; C=CFG['caps']
class Guard:
    def __init__(s, month_spent=0.0, trading_days_left=22):
        s.last_fetch={}     # symbol -> (ns, fetch_id), for skipped:recent
        s.month_spent=month_spent; s.days_left=max(1,trading_days_left); s.day_spent=0.0; s.surges=0; s.requests=0; s.sweep_spent=0.0
        s.allow=min(C['x_daily_usd_cap'], (C['x_monthly_usd_cap']-month_spent)/s.days_left)*C['safety_margin']
    def enabled(s): return bool(CFG.get('fetch_enabled', False))        # v0.3: fetching OFF until Jeffrey/Rose switch it on after the seal
    def recent(s, sym, now_ns):
        """v1.1 x_fetch_status skipped:recent: same symbol fetched within dedupe.reuse_if_last_fetch_within_s -> reuse that fetch_id."""
        lf=s.last_fetch.get(sym)
        return lf[1] if lf and now_ns-lf[0] <= CFG['dedupe']['reuse_if_last_fetch_within_s']*1e9 else None
    def stopped(s): return os.path.exists(os.path.expanduser(C['kill_file'])) or s.month_spent>=C['x_monthly_usd_cap']*C['safety_margin'] or s.day_spent>=s.allow
    def stage(s):
        share=s.day_spent/s.allow if s.allow>0 else 1
        for st in CFG['stages_by_share_of_today_allowance'][:-1]:
            if share<st['until']: return st
        return None
    def precheck(s, kind, max_results=0, n_users=0, big_move=False, thin=False, after_reserve_release=False):
        """kind: 'sweep' | 'crowd' | 'users'. Returns (ok, max_results_to_use, x_fetch_status_if_skipped)."""
        if not s.enabled(): return False, 0, 'disabled'                  # SCHEMAS v1.1: fetching off by config (not skipped:budget / pending)
        if s.stopped(): return False, 0, 'skipped:budget'
        if s.requests>=C['requests_per_day']: return False, 0, 'skipped:cap'
        room=s.allow-s.day_spent
        if kind=='sweep':
            if s.sweep_spent+max_results*P['post_read_usd']>s.allow*C['sweep_budget_share']: return False,0,'skipped:budget'
            return (max_results*P['post_read_usd']<=room), max_results, None if max_results*P['post_read_usd']<=room else 'skipped:budget'
        if kind=='users':
            cost=n_users*P['user_read_usd']; return (cost<=room), n_users, None if cost<=room else 'skipped:budget'
        if s.surges>=C['surge_fetches_per_day']: return False,0,'skipped:cap'
        st=s.stage()
        if st is None: return False,0,'skipped:budget'
        if st['until']>0.6 and not (big_move or (thin and st['until']<=0.85)): return False,0,'skipped:budget'
        reserve=0 if (big_move or after_reserve_release) else C['big_move_reserve_usd']
        mr=min(max_results, st['crowd_max_results'])
        while mr>=10 and mr*P['post_read_usd']>room-reserve: mr-=5      # shrink to fit; X minimum is 10
        if mr<10: return False,0,'skipped:budget'
        return True, mr, None
    def record(s, kind, n_posts=0, n_users=0, sym=None, now_ns=None, fetch_id=None):
        if kind=='crowd' and sym: s.last_fetch[sym]=(now_ns or 0, fetch_id)
        cost=n_posts*P['post_read_usd']+n_users*P['user_read_usd']; s.day_spent+=cost; s.month_spent+=cost; s.requests+=1
        if kind=='crowd': s.surges+=1
        if kind=='sweep': s.sweep_spent+=cost
        return cost
if __name__=="__main__":
    # Simulation over a 22-trading-day cycle using replay-derived sizes: crowd returns 50 (hot) / 25 (typical) / 10 (quiet) posts;
    # ~45% of posts survive stage 1; 60% of survivors' authors need a lookup on day 1, falling to 30% as the 7-day cache warms.
    import random; random.seed(7)
    CFG['fetch_enabled']=True     # simulation only; the config file keeps fetching off
    month=0.0; worst_day=0; days=22; served=skipped=0
    for d in range(days):
        g=Guard(month, days-d); n=random.choice([15,25,35,50,60])
        for k in range(n):
            if k%6==0:
                ok,mr,_=g.precheck('sweep',max_results=random.randint(5,20))
                if ok: g.record('sweep',n_posts=mr)
            big=random.random()<0.25; thin=random.random()<0.4; ret=random.choice([50,25,25,10])
            ok,mr,why=g.precheck('crowd',max_results=50,big_move=big,thin=thin,after_reserve_release=k>n*0.8)
            if not ok: skipped+=1; continue
            posts=min(ret,mr); g.record('crowd',n_posts=posts)
            nu=int(posts*0.45*(0.6 if d<5 else 0.3))
            okU,_,_=g.precheck('users',n_users=nu)
            if okU and nu: g.record('users',n_users=nu)
            served+=1
        month=g.month_spent; worst_day=max(worst_day,g.day_spent)
        print(f"day {d+1:2} surges={n:2} served={g.surges:2} spent=${g.day_spent:5.2f} allow=${g.allow:4.2f} month=${month:6.2f}")
    print(f"cycle total ${month:.2f} (cap $100), worst day ${worst_day:.2f} (cap $5), served {served}, skipped {skipped}")
