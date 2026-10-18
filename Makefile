PDF = build/dissertation.pdf
SRC = $(sort $(wildcard chapters/0*.md))

$(PDF): $(SRC) references.bib templates/header.tex templates/metadata.yaml
	pandoc templates/metadata.yaml $(SRC) -o $(PDF) --pdf-engine=xelatex --citeproc \
	  --bibliography=references.bib -H templates/header.tex --toc \
	  -V geometry:margin=2.5cm -V fontsize=11pt -V linestretch=1.3 -V colorlinks=true --resource-path=.

.PHONY: pdf
pdf: $(PDF)
