import numpy as np
import plotly.graph_objects as go
import polars as pl

#########
# types #
#########

theme = "hsl(236, 94%, 68%)"

##########
# public #
##########


def extract_storms(
    data: pl.DataFrame,
    *,
    wind_threshold: float,
    duration_threshold: float,
    min_time_between_storms: int = 24,
) -> pl.DataFrame:
    # extract individual storms
    data = (
        data.with_columns(
            (pl.col("wind_speed") > wind_threshold).alias("in_storm")
        )
        .with_columns(
            (pl.col("in_storm") != pl.col("in_storm").shift().fill_null(False))
            .cum_sum()
            .alias("storm_id")
        )
        .filter(pl.col("in_storm"))
        .group_by("storm_id")
        .agg(
            pl.col("datetime").min().alias("datetime_start"),
            pl.col("datetime").max().alias("datetime_end"),
            (pl.col("datetime").max() - pl.col("datetime").min())
            .dt.total_hours()
            .alias("duration"),
            pl.col("wind_direction").mode().first(),
            pl.col("wind_speed").mean().alias("wind_speed_mean"),
            pl.col("wind_speed").max().alias("wind_speed_max"),
            pl.col("sea_ice_cover").mean(),
        )
        .sort("datetime_start")
    )
    # combine storms less than 24h apart
    data = (
        data.with_columns(
            (
                (pl.col("datetime_start") - pl.col("datetime_end").shift())
                > min_time_between_storms
            ).alias("sufficient_time")
        )
        .with_columns(pl.col("sufficient_time").cum_sum().alias("group_id"))
        .group_by("group_id")
        .agg(
            pl.col("datetime_start").min(),
            pl.col("datetime_end").max(),
            (pl.col("datetime_end").max() - pl.col("datetime_start").min())
            .dt.total_hours()
            .alias("duration"),
            pl.col("wind_direction").sort_by("duration").last(),
            (pl.col("wind_speed_mean") * pl.col("duration")).sum()
            / pl.col("duration").sum(),
            pl.col("wind_speed_max").max(),
            pl.col("sea_ice_cover").mean(),
        )
        .rename({"group_id": "storm_id"})
    )
    # only keep storms longer than the given duration
    data = data.filter(pl.col("duration") >= duration_threshold)
    return data


def create_mean_residual_life_fig(
    data: pl.DataFrame,
    feature: str,
    *,
    title: str,
    threshold: float | None = None,
) -> go.Figure:
    x = data[feature].sort().to_numpy()
    thresholds = np.arange(np.ceil(x[0]), np.floor(x[-1]), 0.1)
    _x = [x[x > t] - t for t in thresholds]
    residuals = np.array([np.mean(x) for x in _x])
    std = np.array([np.std(x) / np.sqrt(x.shape[0]) for x in _x])
    return go.Figure(
        [
            go.Scatter(
                x=thresholds.tolist() + thresholds.tolist()[::-1],
                y=(residuals - 1.96 * std).tolist()
                + (residuals + 1.96 * std).tolist()[::-1],
                fill="toself",
                fillcolor="hsla(236, 94%, 68%, 0.1)",
                line_width=0,
            ),
            go.Scatter(
                x=thresholds,
                y=residuals,
                line_color=theme,
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
            "showlegend": False,
            "xaxis_title": "Seuil",
            "yaxis_title": "Moyenne des résiduelles",
            "shapes": (
                []
                if threshold is None
                else [
                    {
                        "type": "line",
                        "x0": threshold,
                        "x1": threshold,
                        "y0": 0,
                        "y1": 1,
                        "yref": "paper",
                        "line_color": "red",
                    }
                ]
            ),
            "annotations": (
                []
                if threshold is None
                else [
                    {
                        "showarrow": False,
                        "x": threshold,
                        "y": 1,
                        "yanchor": "bottom",
                        "yref": "paper",
                        "font_color": "red",
                        "text": "Seuil choisi",
                    }
                ]
            ),
        },
    )


def fit_storms(data: pl.DataFrame):
    pass


###########
# private #
###########
