#figure(
  caption: [Paramètres de vagues pour les périodes de retour],
  table(
    columns: (auto, auto, 10em, 10em),
    align: (left, center, center, center),
    inset: (x: 0.25em, y: 0.5em),
    stroke: (x, y) => (
      top: if y == 0 and x < 2 { none } else { 1pt },
      bottom: 1pt,
      left: if x == 1 or (x == 0 and y == 0) { none } else { 1pt },
      right: if x == 0 { none } else { 1pt },
    ),
    [], [], [*50 ans*], [*100 ans*],
    __body__,
  ),
) <tab:wave-params>
