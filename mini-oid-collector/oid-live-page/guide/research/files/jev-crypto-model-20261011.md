# Jev crypto model (RohOnChain): not adopted (2026-10-11)

*Summary note written 2026-10-20 from the desk's 10/11 decision record. There was no separate study file.*

**Question.** Could the "Jev" design (a sub-100 ms crypto buy/sell model shared by RohOnChain) help OID trading?

**What was checked.** The published design and the independent paper tests of its direction calls.

**Result.** The independent tests found its direction calls close to a coin flip: **AUC 0.46–0.49** (0.50 = random). Speed is also not OID's bottleneck: the desk trades minutes to days, not milliseconds.

**Verdict.** Rejected (not worth using). What came out of it: on Jeffrey's go-ahead, the desk started the **confidence log and weekly calibration check** for Hal's and Grok Bot's trade calls (scorekeeping only), and sent Research Bot a five-item wish list (call-wall breaks, expiry pins, weekend/event decay, dip quality, entry timing).
