// Renderiza as formulas \( ... \) e \[ ... \] geradas pelo pymdownx.arithmatex.
document$.subscribe(({ body }) => {
  renderMathInElement(body, {
    delimiters: [
      { left: "$$", right: "$$", display: true },
      { left: "$", right: "$", display: false },
      { left: "\(", right: "\)", display: false },
      { left: "\[", right: "\]", display: true },
    ],
  });
});
