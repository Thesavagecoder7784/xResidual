#!/usr/bin/env bash
# One-shot: snapshot the FINAL group-stage cards into viz/group_stage/ (frozen archive).
# Rebuilds the group-stage card data on the final 72/72 results, re-renders, then copies each
# card's png+html+data into viz/group_stage/ so the group-stage set is grouped and frozen,
# independent of anything the knockouts do to the live viz/model/ cards.
set -uo pipefail
ROOT="/Users/prabhatm/Documents/GitHub/xResidual"
cd "$ROOT"
PY="${PYTHON:-/usr/local/bin/python3}"   # the project interpreter (has sklearn+threadpoolctl); bare python3 is 3.9 and missing deps

echo "== 1. rebuild group-stage data on final results =="
for b in build_group_sim build_incentive build_heat build_travel build_draws_shocks build_vein; do
  $PY scripts/$b.py >/tmp/gs_$b.log 2>&1 && echo "  ok: $b" || echo "  warn: $b (see /tmp/gs_$b.log)"
done

# group-stage cards (NOT softest_road/unequal_prize/confederation_survival — those stay live for the knockouts)
GS="third_place_cutline decisive_games group_openness third_place_lottery group_board bubble \
    draw_luck group_incentive heat_exposure travel_burden draws_shocks goals_record draws_paradox \
    clinch_first dead_rubbers cross_group_butterfly points_first jeopardy_gd"

echo "== 2. re-render each group-stage card on final data =="
cd "$ROOT/viz"
for c in $GS; do
  [ -f "model/$c.html" ] && ./render.sh "model/$c.html" "model/$c.png" >/dev/null 2>&1 && echo "  rendered $c"
done
cd "$ROOT"

echo "== 3. snapshot into viz/group_stage/ =="
mkdir -p viz/group_stage
n=0
for c in $GS; do
  for ext in png html; do
    [ -f "viz/model/$c.$ext" ] && cp "viz/model/$c.$ext" "viz/group_stage/"
  done
  [ -f "viz/group_stage/$c.png" ] && n=$((n+1))
done
# the shared backing data the frozen html reads
for j in _groupsim _drawluck _incentive _heat _travel _draws_shocks _vein; do
  [ -f "viz/model/$j.js" ] && cp "viz/model/$j.js" "viz/group_stage/"
done
echo "FREEZE DONE: $n group-stage cards archived in viz/group_stage/"
