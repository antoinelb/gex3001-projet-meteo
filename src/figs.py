import textwrap

import numpy as np
import plotly.graph_objects as go
import polars as pl

theme = "hsl(236, 94%, 68%)"
other_theme = "hsl(285, 94%, 68%)"

#########
# types #
#########

storm_message = "Une tempête est définie comme un événement avec vents soutenus d'au moins {wind_threshold} m/s et durant au moins {duration_threshold}h. Les tempêtes avec moins de 24h de temps entre les deux sont combinées."

##########
# public #
##########


def create_wind_rose(data: pl.DataFrame, *, title: str) -> go.Figure:
    speed = 10
    data = (
        data.filter(
            pl.col("wind_direction").is_not_null()
            & (pl.col("wind_direction") != 0)
        )
        .group_by(
            "wind_direction",
            (pl.col("wind_speed") / speed).floor().cast(pl.UInt64),
        )
        .len()
        .drop_nulls()
        .sort("wind_direction", "wind_speed", descending=[False, True])
    )
    n_speeds = data["wind_speed"].n_unique()
    colours = [f"hsl(236, 94%, {68 + i * 5}%)" for i in range(n_speeds)]
    speed_names = [
        f"< {speed} m/s" if i == 0 else f"{i*speed}-{(i+1)*speed} m/s"
        for i in range(n_speeds)
    ][::-1]
    return go.Figure(
        [
            *[
                go.Barpolar(
                    r=_data["len"],
                    theta=_data["wind_direction"],
                    marker_color=colours[i],
                    name=speed_names[i],
                    legendgroup=speed_names[i],
                    subplot="polar",
                )
                for i, _data in enumerate(
                    data.partition_by("wind_speed", maintain_order=True)
                )
            ],
            *[
                go.Barpolar(
                    r=_data["len"],
                    theta=_data["wind_direction"],
                    marker_color=colours[i],
                    name=speed_names[i],
                    legendgroup=speed_names[i],
                    showlegend=False,
                    subplot="polar2",
                )
                for i, _data in enumerate(
                    data.partition_by("wind_speed", maintain_order=True)
                )
                if not speed_names[i].startswith("<")
            ],
        ],
        {
            "title": {
                "x": 0.5,
                "y": 1,
                "xanchor": "center",
                "text": title,
                "yanchor": "top",
            },
            "height": 400,
            "width": 800,
            "margin": {"t": 50, "b": 0, "l": 0, "r": 0, "autoexpand": True},
            "font_family": "Playfair Display",
            "barmode": "stack",
            "legend": {
                "y": 1,
                "yanchor": "top",
            },
            "polar": {
                "domain": {"x": [0, 0.45]},
                "radialaxis_showticklabels": False,
                "radialaxis_showline": False,
                "angularaxis_rotation": 90,
                "angularaxis_direction": "clockwise",
            },
            "polar2": {
                "domain": {"x": [0.55, 1]},
                "radialaxis_showticklabels": False,
                "radialaxis_showline": False,
                "angularaxis_rotation": 90,
                "angularaxis_direction": "clockwise",
            },
            "annotations": [
                {
                    "showarrow": False,
                    "x": 0.225,
                    "y": 1,
                    "xref": "paper",
                    "yref": "paper",
                    "xanchor": "center",
                    "yanchor": "bottom",
                    "text": "Rose de tous les vents",
                },
                {
                    "showarrow": False,
                    "x": 0.775,
                    "y": 1,
                    "xref": "paper",
                    "yref": "paper",
                    "xanchor": "center",
                    "yanchor": "bottom",
                    "text": "Rose des vents supérieurs à 10 m/s",
                },
            ],
        },
    )


def create_qq_plot(
    series_1: pl.Series, series_2: pl.Series, *, title: str
) -> go.Figure:
    quantiles = np.linspace(0, 1, 200)
    x = np.quantile(series_1.drop_nulls().sort().to_numpy(), quantiles)
    y = np.quantile(series_2.drop_nulls().sort().to_numpy(), quantiles)
    if np.max(x) > np.max(y):
        line = [np.min(x), np.max(x)]
    else:
        line = [np.min(y), np.max(y)]
    return go.Figure(
        [
            go.Scatter(
                x=line,
                y=line,
                mode="lines",
                line_color=theme,
            ),
            go.Scatter(
                x=x,
                y=y,
                mode="markers",
                marker_color=theme,
            ),
        ],
        {
            "title": {
                "x": 0.5,
                "xanchor": "center",
                "text": title,
            },
            "height": 400,
            "width": 800,
            "margin": {"t": 100, "b": 0, "l": 0, "r": 0, "autoexpand": True},
            "font_family": "Playfair Display",
            "showlegend": False,
            "xaxis_title": series_1.name,
            "yaxis_title": series_2.name,
        },
    )


def create_ice_cover_plot(data: pl.DataFrame) -> go.Figure:
    data = (
        data.group_by(pl.col("datetime").dt.year().alias("year"))
        .agg((pl.col("sea_ice_cover") >= 0.5).mean().alias("iced"))
        .sort("year")
    )
    return go.Figure(
        go.Bar(
            x=data["year"],
            y=data["iced"] * 100,
        ),
        {
            "title": {
                "x": 0.5,
                "xanchor": "center",
                "text": "Évolution du couvert de glace<br>(résolution temporelle mensuelle)",
            },
            "height": 400,
            "width": 800,
            "margin": {
                "t": 50,
                "b": 0,
                "l": 0,
                "r": 0,
                "autoexpand": True,
            },
            "font_family": "Playfair Display",
            "yaxis_title": "Proportion de l'année avec<br>au moins 50% de couvert de glace",
        },
    )


def create_storm_years_fig(
    data: pl.DataFrame, *, wind_threshold: int, duration_threshold: int
) -> go.Figure:
    data = (
        data.group_by(
            pl.col("datetime_start").dt.year().alias("year"),
            (pl.col("sea_ice_cover") >= 0.5).alias("iced"),
        )
        .len()
        .sort("year")
    )
    return go.Figure(
        [
            go.Bar(
                x=data.filter(pl.col("iced"))["year"],
                y=data.filter(pl.col("iced"))["len"],
                name="Avec glace ≥ 50%",
                marker_color=other_theme,
            ),
            go.Bar(
                x=data.filter(~pl.col("iced"))["year"],
                y=data.filter(~pl.col("iced"))["len"],
                name="Avec glace < 50%",
                marker_color=theme,
            ),
        ],
        {
            "title": {
                "x": 0.5,
                "xanchor": "center",
                "text": "Nombre de tempêtes par année",
            },
            "legend": {
                "orientation": "h",
                "x": 0.5,
                "xanchor": "center",
                "y": 1,
                "yanchor": "bottom",
            },
            "height": 400,
            "width": 800,
            "barmode": "stack",
            "margin": {"t": 60, "b": 60, "l": 0, "r": 0, "autoexpand": True},
            "font_family": "Playfair Display",
            "yaxis_title": "Nombre de tempêtes",
            "annotations": [
                {
                    "showarrow": False,
                    "x": 0,
                    "xanchor": "left",
                    "y": 0,
                    "xref": "paper",
                    "yref": "paper",
                    "yanchor": "top",
                    "yshift": -25,
                    "font_size": 10,
                    "align": "left",
                    "text": _wrap_text(
                        storm_message.format(
                            wind_threshold=wind_threshold,
                            duration_threshold=duration_threshold,
                        ),
                        width=100,
                    ),
                }
            ],
        },
    )


def create_storm_intensity_fig(
    data: pl.DataFrame, *, wind_threshold: int, duration_threshold: int
) -> go.Figure:
    data = data.with_columns((pl.col("sea_ice_cover") >= 0.5).alias("iced"))
    return go.Figure(
        [
            go.Scatter(
                x=data.filter(pl.col("iced"))["duration"],
                y=data.filter(pl.col("iced"))["wind_speed_mean"],
                mode="markers",
                name="Avec glace ≥ 50%",
                marker_color=other_theme,
            ),
            go.Scatter(
                x=data.filter(~pl.col("iced"))["duration"],
                y=data.filter(~pl.col("iced"))["wind_speed_mean"],
                mode="markers",
                name="Avec glace < 50%",
                marker_color=theme,
            ),
        ],
        {
            "title": {
                "x": 0.5,
                "xanchor": "center",
                "text": "Distribution de toutes les tempêtes",
            },
            "legend": {
                "orientation": "h",
                "x": 0.5,
                "xanchor": "center",
                "y": 1,
                "yanchor": "bottom",
            },
            "height": 400,
            "width": 800,
            "margin": {"t": 60, "b": 100, "l": 0, "r": 0, "autoexpand": True},
            "font_family": "Playfair Display",
            "xaxis_title": "Durée de la tempête (h)",
            "yaxis_title": "Vitesse de vent moyenne (m/s)",
            "annotations": [
                {
                    "showarrow": False,
                    "x": 0,
                    "xanchor": "left",
                    "y": 0,
                    "xref": "paper",
                    "yref": "paper",
                    "yanchor": "top",
                    "yshift": -50,
                    "font_size": 10,
                    "align": "left",
                    "text": _wrap_text(
                        storm_message.format(
                            wind_threshold=wind_threshold,
                            duration_threshold=duration_threshold,
                        ),
                        width=100,
                    ),
                }
            ],
        },
    )


def create_storm_wind_rose(
    data: pl.DataFrame, *, wind_threshold: int, duration_threshold: int
) -> go.Figure:
    data = (
        data.with_columns((pl.col("sea_ice_cover") >= 0.5).alias("iced"))
        .group_by("wind_direction", "iced")
        .len()
    )
    return go.Figure(
        [
            go.Barpolar(
                r=data.filter(pl.col("iced"))["len"],
                theta=data.filter(pl.col("iced"))["wind_direction"],
                name="Avec glace ≥ 50%",
                marker_color=other_theme,
            ),
            go.Barpolar(
                r=data.filter(~pl.col("iced"))["len"],
                theta=data.filter(~pl.col("iced"))["wind_direction"],
                name="Avec glace < 50%",
                marker_color=theme,
            ),
        ],
        {
            "title": {
                "x": 0.5,
                "y": 0.95,
                "xanchor": "center",
                "text": "Rose des vents des tempêtes<br>(avec la direction la plus fréquente de chaque tempête)",
                "yanchor": "top",
            },
            "legend": {
                "orientation": "h",
                "x": 0.5,
                "xanchor": "center",
                "y": 1,
                "yanchor": "bottom",
            },
            "height": 400,
            "width": 600,
            "margin": {"t": 75, "b": 100, "l": 0, "r": 0, "autoexpand": True},
            "barmode": "stack",
            "font_family": "Playfair Display",
            "polar": {
                "radialaxis_showticklabels": False,
                "radialaxis_showline": False,
                "angularaxis_rotation": 90,
                "angularaxis_direction": "clockwise",
            },
            "annotations": [
                {
                    "showarrow": False,
                    "x": 0,
                    "xanchor": "left",
                    "y": 0,
                    "xref": "paper",
                    "yref": "paper",
                    "yanchor": "top",
                    "yshift": -50,
                    "font_size": 10,
                    "align": "left",
                    "text": _wrap_text(
                        storm_message.format(
                            wind_threshold=wind_threshold,
                            duration_threshold=duration_threshold,
                        ),
                        width=100,
                    ),
                }
            ],
        },
    )


def create_fetch_wind_rose(data: pl.DataFrame) -> go.Figure:
    return go.Figure(
        go.Barpolar(
            r=data["fetch"] / 1000,
            theta=data["wind_direction"],
            marker_color=theme,
        ),
        {
            "title": {
                "x": 0.5,
                "y": 1,
                "xanchor": "center",
                "text": "Rose des fetch",
                "yanchor": "top",
            },
            "height": 400,
            "width": 600,
            "margin": {"t": 50, "b": 75, "l": 0, "r": 0, "autoexpand": True},
            "font_family": "Playfair Display",
            "polar": {
                "radialaxis_showticklabels": True,
                "radialaxis_showline": True,
                "radialaxis_ticksuffix": " km",
                "angularaxis_rotation": 90,
                "angularaxis_direction": "clockwise",
            },
        },
    )


###########
# private #
###########


def _wrap_text(text: str, width: int) -> str:
    return "<br>".join(textwrap.wrap(text, width=width))
