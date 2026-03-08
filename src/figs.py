import numpy as np
import plotly
import plotly.graph_objects as go
import polars as pl

colours = plotly.colors.DEFAULT_PLOTLY_COLORS

##########
# public #
##########


def create_wind_rose(
    data: pl.DataFrame, *, title: str, filter_low_winds: bool = False
) -> go.Figure:
    angle = 45
    speed = 10
    data = (
        data.filter(
            pl.col("wind_direction").is_not_null()
            & (pl.col("wind_direction") != 0)
        )
        .group_by(
            ((pl.col("wind_direction") * 10 + angle / 2) % 360 / angle)
            .floor()
            .cast(pl.UInt64),
            (pl.col("wind_speed") / speed).floor().cast(pl.UInt64),
        )
        .len()
        .drop_nulls()
        .sort("wind_direction", "wind_speed", descending=[False, True])
    )
    n_speeds = data["wind_speed"].n_unique()
    colours = [f"hsl(270, 100%, {80 - i * 10}%)" for i in range(n_speeds)][
        ::-1
    ]
    speed_names = [
        f"< {speed} m/s" if i == 0 else f"{i*speed}-{(i+1)*speed} m/s"
        for i in range(n_speeds)
    ][::-1]
    return go.Figure(
        [
            go.Barpolar(
                r=_data["len"],
                theta=_data["wind_direction"] * angle,
                marker_color=colours[i],
                name=speed_names[i],
            )
            for i, _data in enumerate(
                data.partition_by("wind_speed", maintain_order=True)
            )
            if not filter_low_winds or not speed_names[i].startswith("<")
        ],
        {
            "title": {
                "x": 0.5,
                "xanchor": "center",
                "text": title,
            },
            "barmode": "stack",
            "polar_radialaxis_showticklabels": False,
            "polar_radialaxis_showline": False,
            "polar_angularaxis_rotation": 90,
        },
    )


def create_qq_plot(series_1: pl.Series, series_2: pl.Series) -> go.Figure:
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
                line_color=colours[0],
            ),
            go.Scatter(
                x=x,
                y=y,
                mode="markers",
                marker_color=colours[0],
            ),
        ],
        {
            "title": {
                "x": 0.5,
                "xanchor": "center",
                "text": f"QQ-plot de {series_1.name} et {series_2.name}",
            },
            "showlegend": False,
            "xaxis_title": series_1.name,
            "yaxis_title": series_2.name,
        },
    )
