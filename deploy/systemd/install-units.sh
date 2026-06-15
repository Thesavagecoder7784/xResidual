#!/usr/bin/env bash
# Install + enable the xResidual collection timers. Run ON the VM, after setup.sh and secrets.
#   bash ~/xResidual/deploy/systemd/install-units.sh
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "==> copying units to /etc/systemd/system"
sudo cp "$HERE"/xresidual-*.service "$HERE"/xresidual-*.timer /etc/systemd/system/
sudo systemctl daemon-reload

echo "==> enabling + starting timers"
for t in logger-free logger-orderbooks logger-oddsapi matchwatch tape-cleanup capture-audit; do
  sudo systemctl enable --now "xresidual-$t.timer"
done

echo
echo "Done. Timers:"
systemctl list-timers 'xresidual-*' --no-pager || true
echo
echo "Tail logs with:  tail -f ~/xResidual/logger/data/svc.log"
