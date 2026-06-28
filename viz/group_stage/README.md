# Group-stage cards — frozen archive

These are the **final group-stage cards**, snapshotted when the group stage completed
(2026-06-28, all 72 games played, `group_done: true`). They are a **frozen, grouped set**:
the cards here do **not** update once the knockouts begin — use these for any group-stage
content from here on, not the live `viz/model/` copies.

Each card is captured as its rendered `.png` plus its `.html` and the backing `_*.js` data,
so the archive is self-contained.

## Why a separate frozen copy

Most group-stage cards (cutline, decisive games, openness, lottery, draws, goals, draw-luck,
travel, heat) condition only on group games, so they were already stable. But a few —
the `build_vein` group-stage cards (`clinch_first`, `dead_rubbers`, `cross_group_butterfly`,
`points_first`, `jeopardy_gd`) — are built off a **live knockout-conditioned sim**, so their
live `viz/model/` versions will drift as R32+ games are played. The copies here are the
canonical group-stage versions.

## NOT frozen here (stay live for the knockouts)

`softest_road`, `unequal_prize`, `confederation_survival` — these are knockout-route cards
(also from `build_vein`) and are meant to keep updating as the bracket plays out.

Regenerate this archive with `bash scripts/freeze_group_stage.sh`.
