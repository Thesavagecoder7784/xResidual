#!/usr/bin/env bash
# One-time setup on the VM to publish the live site. Run AFTER the write deploy key
# (~/.ssh/xres_deploy.pub) has been added to the GitHub repo. Idempotent.
set -euo pipefail
REPO="/home/azureuser/xResidual"
PUB="/home/azureuser/xres-pub"
REMOTE="git@github.com:Thesavagecoder7784/xResidual.git"
export GIT_SSH_COMMAND="ssh -i $HOME/.ssh/xres_deploy -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new"

echo "-- verify the deploy key can reach GitHub"
ssh -i "$HOME/.ssh/xres_deploy" -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new -T git@github.com 2>&1 | grep -i "successfully authenticated\|does not provide shell" || true

echo "-- publish clone at $PUB"
if [ ! -d "$PUB/.git" ]; then
  git clone --depth 1 "$REMOTE" "$PUB"
else
  git -C "$PUB" remote set-url origin "$REMOTE"
  git -C "$PUB" pull --rebase --autostash
fi

echo "-- install + start the site timer"
sudo cp "$REPO/deploy/systemd/xresidual-site.service" "$REPO/deploy/systemd/xresidual-site.timer" /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now xresidual-site.timer

echo "-- one immediate refresh to verify end-to-end"
bash "$REPO/deploy/refresh_site_vm.sh"
echo "-- timers:"
systemctl list-timers 'xresidual-*' --no-pager
