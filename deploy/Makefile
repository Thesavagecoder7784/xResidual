# xResidual  ⇄  Azure VM control panel.  Run from the repo root:  make -f deploy/Makefile <target>
# (or symlink:  ln -s deploy/Makefile Makefile  then just  make pull )

VM    := azureuser@57.154.16.193
KEY   := /Users/prabhatm/Downloads/Sportslogging_key.pem
REPO  := /home/azureuser/xResidual
SSH   := ssh -i $(KEY)
RSYNC := rsync -avz -e "ssh -i $(KEY)"

.PHONY: push-code push-secrets pull ssh status logs timers first-deploy

## Push code + source data UP. Never touches collected data (logger/data) or renders (*.png).
push-code:
	$(RSYNC) --exclude '.git/' --exclude '.venv/' --exclude '__pycache__/' \
	         --exclude '*.pyc' --exclude 'logger/data/' --exclude '*.png' \
	         --exclude 'paper/forecasts.jsonl' --exclude 'paper/match_forecasts.jsonl' \
	         --exclude 'paper/match_forecasts_v2.jsonl' \
	         --exclude 'data/cache/wc_scores_overlay.json' --exclude 'data/cache/wc_scores_meta.json' \
	         ./ $(VM):$(REPO)/

## Push secrets UP (run once, or whenever they change). rsync -a preserves the .pem's 600 perms.
push-secrets:
	$(RSYNC) .env $(VM):$(REPO)/.env
	$(RSYNC) logger/config.json $(VM):$(REPO)/logger/config.json
	$(RSYNC) .kalshi_private_key.pem $(VM):$(REPO)/.kalshi_private_key.pem

## Pull collected data DOWN — snapshots, captures, analysis outputs. Run before rendering/posting.
pull:
	$(RSYNC) $(VM):$(REPO)/logger/data/ ./logger/data/

## Open a shell on the VM.
ssh:
	$(SSH) $(VM)

## Timer health + last few log lines.
status:
	$(SSH) $(VM) "systemctl list-timers 'xresidual-*' --no-pager; echo; echo '--- last svc.log ---'; tail -n 6 $(REPO)/logger/data/svc.log 2>/dev/null"

## Tail all VM logs.
logs:
	$(SSH) $(VM) "tail -n 40 $(REPO)/logger/data/*.log"

## Just the active timers.
timers:
	$(SSH) $(VM) "systemctl list-timers 'xresidual-*' --no-pager"

## One-shot first deploy: push code + secrets, then run setup on the VM.
first-deploy: push-code push-secrets
	$(SSH) $(VM) "bash $(REPO)/deploy/setup.sh"
	@echo
	@echo "Now smoke-test + install timers on the VM:"
	@echo "  make -f deploy/Makefile ssh"
	@echo "  cd ~/xResidual/logger && ../.venv/bin/python run.py --venues polymarket,kalshi   # expect 'ok'"
	@echo "  bash ~/xResidual/deploy/systemd/install-units.sh"
