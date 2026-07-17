# Reproduce the paper. See REPRODUCING.md for the full claim -> script map.
.PHONY: check macros paper test figures

# Verify paper numbers match the JSONs, and run the suite (also the CI gate).
check: macros
	python scripts/emit_macros.py --check
	python -m pytest tests/ -q

# Regenerate the canonical LaTeX macros from writeups/_*_results.json.
macros:
	python scripts/emit_macros.py

# Emit macros, then build the PDF (needs a TeX distribution / latexmk).
paper: macros
	cd paper/arxiv && latexmk -pdf main.tex

test:
	python -m pytest tests/ -q

# TODO: generate the four publication figures into paper/arxiv/figures/.
figures:
	@echo "figures target not yet implemented — see REPRODUCING.md"
