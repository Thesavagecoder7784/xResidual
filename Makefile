# Reproduce the paper. See REPRODUCING.md for the full claim -> script map.
.PHONY: check macros paper test figures

# Verify paper numbers match the JSONs, and run the suite (also the CI gate).
#
# --strict is the half that survives in CI. `macros` regenerates macros.tex immediately above,
# so --check can only ever compare a file against what just wrote it; the real question there is
# whether every macro came from a shipped artifact rather than a hard-coded fallback. --check
# still earns its place locally, where macros.tex persists between runs and can go stale.
check: macros
	python scripts/emit_macros.py --check
	python scripts/emit_macros.py --strict
	python -m pytest tests/ -q

# Regenerate the canonical LaTeX macros from writeups/_*_results.json.
macros:
	python scripts/emit_macros.py

# Emit macros, then build the PDF. Uses whichever TeX driver is present, in preference order:
#   latexmk    — handles the bibtex/rerun loop itself (TeX Live full; NOT in BasicTeX)
#   tectonic   — self-contained, downloads missing packages on demand
#   pdflatex   — manual bibtex + rerun loop (works on a bare BasicTeX)
# macOS note: MacTeX/BasicTeX put binaries in /Library/TeX/texbin, which is on the PATH of a
# login shell but not always of a non-interactive one, so prepend it before probing.
paper: macros
	@export PATH="/Library/TeX/texbin:$$PATH"; cd paper/arxiv && \
	if command -v latexmk >/dev/null 2>&1; then \
		echo "-> latexmk"; latexmk -pdf main.tex; \
	elif command -v tectonic >/dev/null 2>&1; then \
		echo "-> tectonic"; tectonic -X compile main.tex; \
	elif command -v pdflatex >/dev/null 2>&1; then \
		echo "-> pdflatex (manual bibtex loop)"; \
		pdflatex -interaction=nonstopmode main.tex >/dev/null && \
		(bibtex main >/dev/null || true) && \
		pdflatex -interaction=nonstopmode main.tex >/dev/null && \
		pdflatex -interaction=nonstopmode main.tex | tail -3; \
	else \
		echo "No TeX driver found. Install one of:"; \
		echo "  brew install --cask basictex   (then: sudo tlmgr install latexmk siunitx natbib)"; \
		echo "  brew install tectonic          (self-contained, no tlmgr needed)"; \
		exit 1; \
	fi
	@echo "PDF: paper/arxiv/main.pdf"

test:
	python -m pytest tests/ -q

# Regenerate the four publication figures into paper/arxiv/figures/ from the committed JSONs.
figures:
	python scripts/build_paper_figures.py
