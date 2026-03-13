// {{{ preamble

#set page(
  margin: (x: 2.0cm, y: 2.0cm),
)
#set text(lang: "fr")
#set text(font: "New Computer Modern", size: 11pt)
#set par(
  justify: true,
  leading: 0.52em,
  first-line-indent: 1em,
)
#set math.equation(numbering: "(1)")

#show heading: set align(left)

#show heading: it => {
  it
  par(first-line-indent: 1em)[]
}
#show figure: it => {
  it
  par(first-line-indent: 1em)[]
}

#show math.equation.where(block: true): it => {
  if it.has("label") and it.label == <small> {
    set text(size: 8pt)
    it
  } else {
    it
  }
}

#show math.ast: math.dot.op

#show figure.where(kind: table): set figure.caption(position: top)

#show ref: it => {
  if it.element != none {
    let elem = it.element
    if elem.func() == figure {
      let nums = counter(figure.where(kind: elem.kind)).at(elem.location())
      numbering("1", ..nums) // Forces simple number format
    } else if elem.func() in (math.equation, table) {
      let nums = counter(elem.func()).at(elem.location())
      numbering("1", ..nums) // Forces simple number format
    } else {
      it
    }
  } else {
    it
  }
}
#show outline.entry: it => {
  if it.element.func() == figure {
    let fig = it.element
    let cap = fig.caption

    if cap != none and cap.has("body") {
      let body = cap.body
      let clean = if body.has("children") {
        body.children.filter(c => c.func() != footnote).join()
      } else {
        body
      }

      let supplement = fig.supplement
      let num = numbering(fig.numbering, ..counter(figure.where(kind: fig.kind)).at(fig.location()))

      block[
        #link(fig.location())[#supplement #num: #clean]
        #box(width: 1fr, repeat[.])
        #it.page()
      ]
    } else {
      it
    }
  } else {
    it
  }
}

#show <_>: set math.equation(numbering: none)

#let in-outline = state("in-outline", false)

#show outline: it => {
  in-outline.update(true)
  it
  in-outline.update(false)
}

#let flex-caption(long, short) = context if in-outline.get() { short } else { long }

// }}}

#align(center)[
  #text(size: 18pt, weight: "bold")[Analyse météorologique de la côte près du CPE La Ramée aux Îles-de-la-Madeleine]
]

= Source des données

Il y a plusieurs stations météorologiques près du point d'intérêt dont les données sont fournies par Environnement et Changement Climatique Canada (ECCC)#footnote[https://api.weather.gc.ca/collections/climate-hourly].
La plus proche (7052960) se situe à 1.92 km au Nord, mais ses données arrêtent en 1983.
La station encore ouverte la plus proche (7053KGR) se situe à 9.83 km au Nord-Est, avec des données collectées depuis 1993.
Ces stations collectent entre autres les variables suivantes à chaque heure:
- température de l'air à 2 m
- vitesse moyenne du vent
- direction du vent (au 10°)
- précipitation totale

Une autre source de données importante est la réanalyse ERA5 du projet Copernicus dont les données horaires#footnote[https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels-timeseries] sont disponibles pour les variables suivantes:
- composante Est-Ouest du vent à 10 m
- composante Nord-Sud du vent à 10 m
- température de surface de l'eau
- température de l'air à 2 m
De plus, il est aussi possible d'obtenir la moyenne du couvert de glace mensuel#footnote[https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels-monthly-means].
Le couvert aurait pu aussi être obtenu à chaque heure comme les autres variables, mais celui-ci n'est pas préalablement calculé comme série temporelle et aurait nécessité un téléchargement plus complexe (tout comme pour des données quotidiennes).
Comme le couvert de glace n'est pas quelque chose qui varie rapidement, la moyenne mensuelle a été jugée suffisante pour la conception.
Il est à noté que la réanalyse ERA5 a une résolution 0.25° x 0.25°, soit environ 31 km x 31 km, sur les océans, et est donc utile à des fins de comparaison, pour établir des tendances ou pour des variables relativement stables sur de grandes surfaces.

Finalement, les données bathymétriques de la région autour des Îles-de-la-Madeleine a été obtenu du _General Bathymetric Chart of the Oceans_ (GEBCO)#footnote[https://betadownload.gebco.net/] pour pouvoir calculer le fetch dans chacune des directions.

= Analyse des conditions de vent et de tempête

== Détermination des données de vent

La première étape est de déterminer les données de vent les plus fiables entre les deux stations.
Puisque les données des deux stations ne se chevauchent pas, les données d'ERA5 servent de point de comparaison pour déterminer la station à choisir.
La figure~@fig:bias montre qu'au niveau de la direction du vent, les deux stations ont des distributions similaires des vents plus extrêmes, soit ceux de plus de 10 m/s.
Puisque les conditions de conception dépendent des situations extrêmes, ce sont ces vents qui sont plus importants que les vents ordinaires plus fréquents.
On y voit aussi que la distribution des vents d'ERA5 est plus éparpillée, ce qui a du sens puisque ce sont tous les vents dans une région de 31 km par 31 km.
Là où il y a une différence importante entre les deux stations est au niveau des vitesses de vent, en particulier dans les extrêmes.
La station 7052960 dont la fin des données remontent à 1983 montrent des vents beaucoup plus hauts que celle avec des données récentes (7053KGR).
Cependant, on voit aussi qu'il y a une différence importante avec les vitesses d'ERA5 alors que les données plus récentes semblent suivre une distribution plus similaire, avec le biais vers des vents plus forts chez ERA5 provenant sûrement du fait qu'une grande région d'océan est comparée à une station sur la côte.
Parce que les données récentes sont alignées avec celles d'ERA5 et parce que les données plus anciennes ont souvent été prises avec des méthodologies ou des instruments de mesures différents, ce seront les données de la station ouverte 7053KGR qui seront utilisées pour la conception.

#figure(
  caption: "Comparaison des vitesses et directions de vent entre les deux stations et ERA5",
  grid(
    columns: 2,
    gutter: 1em,
    image("figures/closest_rose_des_vents.svg"), image("figures/closest_latest_qq.svg"),
    image("figures/latest_rose_des_vents.svg"), image("figures/closest_era5_qq.svg"),
    image("figures/era5_rose_des_vents.svg"), image("figures/latest_era5_qq.svg"),
  ),
) <fig:bias>

== Choix de la tempête de conception

Un facteur important qui aura de l'influence sur l'impact des vagues est le couvert de glace.
La figure~@fig:ice montre celui-ci à travers les années où de façon arbitraire, la glace est jugée suffisante pour atténuer les vagues lorsque qu'elle couvre au moins 50% de la zone.
On y voit clairement que le couvert de glace diminue rapidement avec les années, ce qui continuera d'empirer avec les changements climatiques~@ouranos_glace.
Bien que cette couverture sous-estime la couverture réelle compte tenu que cette couverture provient des données d'ERA5 et est donc pour une zone de 31 km x 31 km, elle est suffisante pour voir les tendances.

#figure(
  caption: "Distribution des tempêtes",
  [#image(width: 70%, "figures/ice_cover.svg")],
) <fig:ice>

La figure~@fig:storms montre la distribution de toutes les tempêtes ayant été mesurées par la station 7053KGR.
Ici, une tempête est définie comme un événement durant au moins 12 heures durant lequel la vitesse des vents a systématiquement été supérieure à 10 m/s.
Deux tempêtes à moins de 48h d'intervalle sont combinées puisqu'il est assumée qu'elles font partie du même système et auront toutes deux une influence sur les vagues~@lob2022.
Ceci permet de capturer plusieurs tempêtes par année et avoir une bonne idée de leur distribution.
On y voit que la quantité de tempêtes ne semble pas varier à travers les années ce qui est cohérent avec les études récentes qui observent qu'il y n'y a pas de tendance de changement fiable pour la direction ou l'intensité des vents au Québec~@ouranos_vents_1.
Par ailleurs, les modèles climatiques ont encore tendance à sous-estimer la vitesse des vents violents et l'intensité des tempêtes au Québec et donc aucune projection n'est fiable pour caractériser une évolution de ceux-ci~@ouranos_vents_2.
C'est donc les données historiques qui seront utilisées quant à la direction et la vitesse des vents.

Puisque le couvert de glace diminue avec les années et que les tempêtes les plus intenses et les plus longues ne se sont pas produits systématiquement lorsque le couvert de glace était supérieur à 50%, soit le seuil que nous avons établi pour un couvert suffisant, toutes les tempêtes seront considérées pour établir la tempête de conception.

#figure(
  caption: "Distribution de toutes les tempêtes",
  grid(
    columns: 2,
    gutter: 1em,
    align: center,
    image("figures/storm_n.svg"), image("figures/storm_intensity.svg"),
    grid.cell(colspan: 2, image(width: 50%, "figures/storm_wind_rose.svg")),
  ),
) <fig:storms>

La figure~@fig:fetch montre que le fetch est très limité dans la plupart des directions et plus particulièrement dans les directions de fort vent.
En effet, sauf pour l'Est (90°) et le Sud-Est (135°), seules de petites vagues pourront être créées.
Bien que celles-ci puissent affecter le transport sédimentaire, elles seront négligées pour se concentrer uniquement sur les vagues ayant un plus grand potentiel destructeur.

#figure(
  caption: "Distribution des fetch",
  image(width: 50%, "figures/fetch.svg"),
) <fig:fetch>

La distribution des tempêtes provenant des directions de grand fetch est montrée à la figure~@fig:fetch-storms.
Comparé à la distribution de toutes les tempêtes, les vitesses moyennes des vents des tempêtes de grand fetch sont les mêmes, mais leurs durées sont beaucoup plus courtes.

#figure(
  caption: "Distribution des tempêtes venant des directions de grand fetch",
  grid(
    columns: 2,
    gutter: 1em,
    align: center,
    image("figures/east_storm_n.svg"), image("figures/east_storm_intensity.svg"),
    grid.cell(colspan: 2, image(width: 50%, "figures/east_storm_wind_rose.svg")),
  ),
) <fig:fetch-storms>

La tempête de conception utilisée sera définie par sa vitesse de vent moyenne et sa durée.

Les figures~@fig:fit-speed et @fig:fit-duration montre les ajustements de différentes distributions de valeurs extrêmes.
L'évaluation de celles-ci est faite en mesurant la différence entre les quantiles observés et théoriques du maximum annuel des tempêtes et la droite d'ajustement parfait, à la fois sur toutes les tempêtes maximales et sur les 25% tempêtes supérieures.
L'évaluation sur les 25% tempêtes les plus fortes est retenue puisqu'elle correspond mieux à ce qui est visé avec les périodes de retour.
Seules les 4 meilleurs ajustements sont montrés parmi les 34 faits avec diverses distributions pou chacune des variables.
C'est donc la GEV utilisant les 3 maximums annuels qui est utilisé pour établir les périodes de retour de la vitesse moyenne de vent de la tempête et la GPD avec un seuil de quantile 40% pour la durée de celle-ci.

Deux périodes de retour sont considérées, soit 50 et 100 ans.
La période de retour de 100 ans est plus sécuritaire, mais celle-ci est au-delà de la limite de 2-3 fois la durée des données recommandée~@cem[p.~II-8-13].
Ceci permet d'établir les valeurs de périodes de retour présentées au tableau~@tab:storm-return.

#figure(
  caption: "QQ-plot des 4 meilleurs ajustements de distributions à la vitesse de vent des tempêtes maximales annuelles",
  grid(
    columns: 2,
    image("figures/speed_fit_1.svg"), image("figures/speed_fit_2.svg"),
    image("figures/speed_fit_3.svg"), image("figures/speed_fit_4.svg"),
  ),
) <fig:fit-speed>

#figure(
  caption: "QQ-plot des 4 meilleurs ajustements de distributions à la durée des tempêtes maximales annuelles",
  grid(
    columns: 2,
    image("figures/duration_fit_1.svg"), image("figures/duration_fit_2.svg"),
    image("figures/duration_fit_3.svg"), image("figures/duration_fit_4.svg"),
  ),
) <fig:fit-duration>

#include "figures/storm_return_periods.typ"

Une voit les vitesses de vent obtenues, il faut aussi déterminer comment ajuster celles-ci par rapport au fait que les vents seront plus rapides au-dessus de l'océan que sur terre où ils ont été mesurés.
La figure~@fig:air-sea-diff-1 permet de déterminer un ratio d'amplification en fonction de la différence de température de l'air et de la mer.
Comme pour la vitesse de vent et la durée, une distribution a été ajustée aux données du lieu d'intérêt, mais cette fois-ci à partir des données de réanalyse d'ERA5 puisqu'aucune station proche ne collectait les données de température de la mer.
Le meilleur ajustement, déterminé à partir de la statistique d'Anderson-Darling, à ces données était la distribution T non centrée et les périodes de retour minimales sont considérées pour cette différence plutôt que le maximum puisque ce sont celles-ci qui mèneront aux valeurs les plus conservatrices pour la conception.
Le tableau~@tab:diff-return montre ces résultats avec le ratio d'amplification associé.

#figure(
  image("figures/air-sea_adjustment.png", width: 50%),
  caption: flex-caption(
    [Ratio d'amplification permettant de prendre en compte les différences de température air-mer~@shore[p.~3-31]],
    [Ratio d'amplification permettant de prendre en compte les différences de température air-mer],
  ),
) <fig:air-sea-diff-1>

#figure(
  image("figures/air-sea_diff.svg"),
  caption: [Distribution des différences de température air-mer à partir des données d'ERA5 pour le lieu d'intérêt],
) <fig:air-sea-diff-2>

#include "figures/diff_return_periods.typ"


= Calcul des vagues de conception

En combinant les différentes variables de tempête, on peut établir des vagues pour les différentes périodes de retour à l'aide des équations théoriques de la méthode JONSWAP.
À partir des données de fetch $F$ (m), de la durée de tempête $t$ (s), de la vitesse de vent moyenne $U'$ (m/s) et du ratio d'amplification $R_T$ (-), les paramètres suivants sont calculés:
$
     H_(m 0) & = (U^2 H_(m 0)^\*) / g #h(4em) && T_p          && = (U T_p^\*) / g \
           U & = R_T U' #h(4em)               && F^\*         && = (g F) / U^2 \
        t^\* & = (g t) / U
               #h(4em)                        && F^\*_(e f f) && = (t^\* / 68.8)^(3/2) \
  H_(m 0)^\* & = cases(
                 0.0016 (F^\*)^(1/2) "if" F^\* < F_(e f f)^\*,
                 0.0016 (F_(e f f)^\*)^(1/2) "if" F^\* >= F_(e f f)^\*,
               ) #h(4em)                      && T_p^\*       && = cases(
                                                                   0.286 (F^\*)^(1/3) "if" F^\* < F_(e f f)^\*,
                                                                   0.286 (F_(e f f)^\*)^(1/3) "if" F^\* >= F_(e f f)^\*,
                                                                 )
$
où $g$ est la constante gravitationnelle de 9.81 m/s#super[2].
Il faut aussi prendre en compte que physiquement, les paramètres $H_(m 0)^\*$ et $T_p^\*$ peuvent être au maximum 0.243 et 8.13.

#include "figures/wave_params.typ"

= Autres facteurs importants

D'autres facteurs météorologiques pourraient être importants lors de la conception, soit la pression qui affecte le niveau d'eau, les précipitations et températures qui pourraient affecter des infrastructures végétalisées.

La figure~@fig:pressure montre la distribution des pressions et le tableau~@tab:pressure-return les pires pressions qui peuvent être attendues.

#figure(
  caption: [Distribution de la pression atmosphérique à la station 7053KGR],
  image("figures/pressures.svg"),
) <fig:pressure>

#include "figures/pressure_return_periods.typ"

La figure~@fig:precipitation-temperature montre la distribution des précipitations journalières lors des journées pluvieuses, soit 16.8% des journées en moyenne, et la distribution des températures horaires.

#figure(
  caption: [Distribution de la précipitation journalière et de la température horaire à la station 7053KGR],
  grid(
    columns: 2,
    image("figures/precipitation.svg"), image("figures/temperature.svg"),
  ),
) <fig:precipitation-temperature>


#bibliography("references.bib", style: "apa")
