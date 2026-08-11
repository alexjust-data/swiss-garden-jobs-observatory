# GATE-011C-4 dedup review audit v0.1

This gate adds one unresolved, noncritical review and no AUTO_MERGE.

| Decision | Pair | Sources | Titles | Employers | Locations | Score | Feature scores | Reason |
|---|---|---|---|---|---|---|---|---|
| `de1599c9-26da-4975-aef7-b3c8c0d7e2ed` | `6421` / `6422` | SG canton / SG canton | Praktikant/in Kreisgericht Werdenberg-Sarganserland / same | Gerichte / Gerichte | Mels / Mels | 0.8431 | title 1.0000; employer 1; location 1; text 0.9655; contact/requisition 0; pensum/start 0 | Separate native IDs and materially different start periods (July 2027 versus March 2027) provide no hard identity key. GATE-008 correctly refuses an automatic merge. |

Hard barriers are empty. The pair remains `REVIEW`; C-4 does not resolve it.
