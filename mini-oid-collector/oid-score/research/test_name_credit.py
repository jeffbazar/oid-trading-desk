import sys; sys.path.insert(0, "/Users/jake/oid-score/research")
import name_credit as N
s1="Credit stress is SKYROCKETING among US AI companies:\n\nCoreWeave, $CRWV, 5-year credit default swap (CDS) spread surged +135 basis points on Wednesday, to a record ~1,118 basis points, implying a 63% probability of default within 5 years.\n\nAt the same time, the company\u2019s 2032 bonds have fallen to ~78 cents on the dollar, yielding more than 15%, while its shares plunged as much as -17%, to near their lowest level since May 2025.\n\n$CRWV CDS has now surged over 500 basis points since November 2025.\n\nMeanwhile, Oracle, $ORCL, 5-year CDS widened to a record 288 basis points, up from 260 bps a week earlier.\n\nDefault insurance costs have also risen to record highs for Amazon, $AMZN, Alphabet, $GOOGL, Meta, $META, and Nvidia, $NVDA."
s2="CoreWeave\u2019s DEFAULT RISK is exploding higher:\n\nCoreWeave, $CRWV, 5-year credit default swap (CDS) spread surged as much as +74.5 basis points on Thursday, to a record 1,194.5 basis points, implying a more than 60% probability of default within 5 years.\n\nMeanwhile, its 9% bonds due 2031 fell ~0.5 cents on the dollar to 82.75 cents, pushing yields to 14.5%."
r1=N.parse_post(s1,"2026-10-15T13:14:00.000Z"); r2=N.parse_post(s2,"2026-10-16T14:01:41.000Z")
for r in r1+r2: r.pop("snippet"); print(r)
c=[r for r in r1 if r["ticker"]=="CRWV"][0]; o=[r for r in r1 if r["ticker"]=="ORCL"][0]; c2=r2[0]
assert (c["level_bp"],c["level_approx"],c["change_bp"],c["refers_date"])==(1118.0,1,135.0,"2026-10-14")
assert (o["level_bp"],o["prior_bp"],o["refers_date"])==(288.0,260.0,"2026-10-14")
assert (c2["level_bp"],c2["level_approx"],c2["change_bp"],c2["change_approx"],c2["refers_date"])==(1194.5,1,74.5,1,"2026-10-15")
print("SEED TESTS PASS")
