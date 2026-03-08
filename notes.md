Explications des variables: https://www.canada.ca/en/environment-climate-change/services/climate-change/canadian-centre-climate-services/display-download/technical-documentation-hourly-data.html

- une direction de vent de 0 indique un vent calme
- à l'origine, la vitesse du vent est en km/h et est prise à 10 m au-dessus du sol

## todo

- [x] calculer biais entre les deux stations
- [x] calculer biais entre les deux stations et ERA5
- [x] ajouter ERA5 pour le passé (pour les deux stations)
- [ ] ajouter fetch
- [x] calculer tempêtes et temps de tempête

## Notes

Les vents ne seront pas plus importants dans le futur selon les études récentes.
https://www.ouranos.ca/en/climate-phenomena/winds-and-storms-projected-changes
https://www.ouranos.ca/en/climate-phenomena/winds-and-storms-observed-changes

Les données bathymétriques ont été téléchargées de https://betadownload.gebco.net/

## Analyse

- Proportion de glace moyenne par saison
- Direction et vitesse de vent par saison
- Biais entre closest, latest et era5
    - choisir latest
- Durée et vitesse moyenne des tempêtes par saison
    - montrer biais d'era5
- fetch et ajustement pour température
