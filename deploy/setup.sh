#!/usr/bin/env bash
# xResidual VM setup — run ONCE on the Azure VM, after the code has been synced up.
#   (from your laptop)  make push-code
#   (then on the VM)    ssh ... ; bash ~/xResidual/deploy/setup.sh
#
# Idempotent: safe to re-run. Installs swap, system deps, and the Python venv.
set -euo pipefail

REPO="$HOME/xResidual"
VENV="$REPO/.venv"

echo "==> 1/4  swap (2 GB) — this box has ~900 MB RAM, swap prevents OOM kills"
if ! sudo swapon --show | grep -q '/swapfile'; then
  sudo fallocate -l 2G /swapfile
  sudo chmod 600 /swapfile
  sudo mkswap /swapfile
  sudo swapon /swapfile
  grep -q '/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
  echo "    swap on (persisted in /etc/fstab)."
else
  echo "    swap already present, skipping."
fi

echo "==> 2/4  apt deps"
sudo apt-get update -qq
sudo apt-get install -y -qq python3-venv python3-pip rsync

echo "==> 3/4  python venv + packages"
python3 -m venv "$VENV"
"$VENV/bin/pip" install --upgrade pip -q
# collection: requests/cryptography (Kalshi signing), websockets/certifi (capture)
# analysis (capture --analyze): numpy/scipy/pandas/statsmodels
"$VENV/bin/pip" install -q \
  requests cryptography websockets certifi \
  numpy scipy pandas statsmodels
echo "    venv ready at $VENV"

echo "==> 4/4  data dir"
mkdir -p "$REPO/logger/data"

echo
echo "Setup done. Next:"
echo "  1. make sure secrets are present:  $REPO/.env  $REPO/logger/config.json  $REPO/.kalshi_private_key.pem"
echo "  2. smoke-test one logger pass:      cd $REPO/logger && $VENV/bin/python run.py --venues polymarket,kalshi"
echo "  3. install the timers:              bash $REPO/deploy/systemd/install-units.sh"
