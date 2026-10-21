# UI mockups (2026-10-21)

Three screens from section 9 of `../../SCALING-STRATEGY-20261021.md`, drawn as Claude Design artboards. The canvas is at https://claude.ai/artifact/Tzyt9orGYCesVS7vgAWn3g; these files are its source.

| File | Screen | Size |
|---|---|---|
| `Main.dc.html` | Execution cockpit for 6:30 AM to 1:00 PM PT: status bar with feed ages and the kill switch, the Now lane (at most five candidates from the surge engine), active-name tiles, sector strip, focus panel, ticket, positions, decision log | 1440 by 960 |
| `Ticket.dc.html` | Focus panel and decision ticket: action, confidence, reasons, quantity, bracket (target, stop, time stop), live debit and break-even, capture mode. Interactive on the canvas | 1280 by 960 |
| `Scorecard.dc.html` | Research tab, first screen: the 10/20 numbers as KPI tiles, conditioner lifts, momentum-state bars, calibration strip, promotion ladder, lane and latency and archive coverage | 1440 by 1080 |
| `canvas.json` | Board positions, sizes and titles | |

Each file loads `./support.js`, the canvas runtime, which is not in this repository. Opened directly in a browser the boards render statically (the ticket's live arithmetic needs the runtime). The numbers on the boards are the 10/20 study and ledger figures from the main report, plus the owner's 10/20 fills; the candidate names in the Now lane are the surge alerts from the same session. Dark palette: background `#0f1419`, surface `#171d25`, amber `#f5a524` for volume, blue `#4c9aff` for calls and up moves, orange `#ff7a45` for puts and down moves.
