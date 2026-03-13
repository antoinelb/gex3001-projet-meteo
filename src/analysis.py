from pathlib import Path
from typing import Callable

import numpy as np
import numpy.typing as npt
import plotly.graph_objects as go
import polars as pl
import scipy.stats as st

#########
# types #
#########

theme = "hsl(236, 94%, 68%)"
templates_dir = Path(__file__).parent / ".." / "templates"
figures_dir = Path(__file__).parent / ".." / "figures"

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


def fit_storms(data: pl.DataFrame, feature: str) -> list[
    tuple[
        str,
        float,
        float,
        Callable[[npt.NDArray[np.float64]], npt.NDArray[np.float64]],
    ]
]:
    fits = [
        *[_fit_storms_with_gev(data, feature, n_max) for n_max in range(1, 5)],
        *[
            _fit_storms_with_gumbel(data, feature, n_max)
            for n_max in range(1, 5)
        ],
        *[
            _fit_storms_with_weibull(data, feature, n_max)
            for n_max in range(1, 5)
        ],
        *[
            _fit_storms_with_ged(data, feature, threshold)
            for threshold in np.arange(0, 1, 0.1)
        ],
        *[
            _fit_storms_with_exponential(data, feature, threshold)
            for threshold in np.arange(0, 1, 0.1)
        ],
        _fit_storms_with_lognormal(data, feature),
        _fit_storms_with_normal(data, feature),
    ]

    annual_max = (
        data.group_by(pl.col("datetime_start").dt.year())
        .agg(pl.col(feature).max())[feature]
        .to_numpy()
    )

    return [
        (
            name,
            _calculate_qq_rmse(annual_max, get_quantiles),
            _calculate_qq_rmse(annual_max, get_quantiles, threshold=0.9),
            get_quantiles,
        )
        for name, get_quantiles in fits
    ]


def create_storms_qq_plot(
    data: pl.DataFrame,
    feature: str,
    feature_name: str,
    distribution: tuple[
        str,
        float,
        float,
        Callable[[npt.NDArray[np.float64]], npt.NDArray[np.float64]],
    ],
) -> go.Figure:
    quantiles = np.arange(0.01, 1, 0.01)
    name, qq_rmse, qq_rmse_top_25, _get_quantiles = distribution
    y = (
        data.group_by(pl.col("datetime_start").dt.year())
        .agg(pl.col(feature).max())[feature]
        .to_numpy()
    )
    y = np.quantile(y, quantiles)
    x = _get_quantiles(quantiles)

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
                "text": f"{feature_name}<br>{name}",
            },
            "height": 400,
            "width": 800,
            "margin": {"t": 75, "b": 0, "l": 0, "r": 0, "autoexpand": True},
            "font_family": "Playfair Display",
            "font_size": 18,
            "showlegend": False,
            "xaxis_title": "<i>q</i><sub>théorique</sub>",
            "yaxis_title": "<i>q</i><sub>observations</sub>",
            "annotations": [
                {
                    "showarrow": False,
                    "x": 0,
                    "y": 1,
                    "xref": "paper",
                    "yref": "paper",
                    "xshift": 5,
                    "align": "left",
                    "text": f"RMSE = {qq_rmse:.2f}",
                },
                {
                    "showarrow": False,
                    "x": 0,
                    "y": 0.9,
                    "xref": "paper",
                    "yref": "paper",
                    "xshift": 5,
                    "align": "left",
                    "text": f"RMSE (top 25%) = {qq_rmse_top_25:.2f}",
                },
            ],
        },
    )


def calculate_storm_return_periods(
    wind_speed_get_quantiles: Callable[
        [npt.NDArray[np.float64]], npt.NDArray[np.float64]
    ],
    duration_get_quantiles: Callable[
        [npt.NDArray[np.float64]], npt.NDArray[np.float64]
    ],
    return_periods: list[int] = [50, 100],
) -> pl.DataFrame:
    return pl.DataFrame(
        [
            _calculate_storm_return_period(
                wind_speed_get_quantiles, duration_get_quantiles, return_period
            )
            for return_period in return_periods
        ]
    )


def create_land_sea_diff_fig(
    data: pl.DataFrame,
) -> tuple[go.Figure, Callable[[float], float]]:
    diff = (
        data.select(
            pl.col("land_temperature") - pl.col("sea_surface_temperature")
        )[:, 0]
        .sample(10_000)
        .to_numpy()
    )
    norm_params = st.norm.fit(diff)
    skewnorm_params = st.skewnorm.fit(diff)
    nct_params = st.nct.fit(diff)
    norm_ad = _calculate_anderson_darling(
        diff, lambda x: st.norm.cdf(x, *norm_params)
    )
    skewnorm_ad = _calculate_anderson_darling(
        diff, lambda x: st.skewnorm.cdf(x, *skewnorm_params)
    )
    nct_ad = _calculate_anderson_darling(
        diff, lambda x: st.nct.cdf(x, *nct_params)
    )
    x = np.linspace(diff.min(), diff.max(), 1000)

    def _get_quantiles(q: float) -> float:
        return st.nct.ppf(q, *nct_params)

    return (
        go.Figure(
            [
                go.Histogram(
                    x=diff,
                    histnorm="probability density",
                    nbinsx=200,
                    name="Densité",
                ),
                go.Scatter(
                    x=x,
                    y=st.norm.pdf(x, *norm_params),
                    name=f"Normale (<i>A</i><sup>2</sup> = {norm_ad:.2f})",
                ),
                go.Scatter(
                    x=x,
                    y=st.skewnorm.pdf(x, *skewnorm_params),
                    name=f"Normale asymétrique (<i>A</i><sup>2</sup> = {skewnorm_ad:.2f})",
                ),
                go.Scatter(
                    x=x,
                    y=st.nct.pdf(x, *nct_params),
                    name=f"T non centrée (<i>A</i><sup>2</sup> = {nct_ad:.2f})",
                ),
            ],
            {
                "height": 400,
                "width": 800,
                "margin": {
                    "t": 0,
                    "b": 0,
                    "l": 0,
                    "r": 0,
                    "autoexpand": True,
                },
                "font_family": "Playfair Display",
                "font_size": 18,
                "legend": {
                    "x": 0,
                    "xanchor": "left",
                    "bgcolor": "rgba(0,0,0,0)",
                },
                "xaxis_title": "Différence de température air-mer (<i>T</i><sub>a</sub> − <i>T</i><sub>m</sub>) °C",
                "yaxis_title": "Densité",
            },
        ),
        _get_quantiles,
    )


def create_pressure_fig(
    data: pl.DataFrame,
) -> tuple[go.Figure, Callable[[float], float]]:
    _data = data["pressure"].drop_nulls().sample(10_000).to_numpy()
    norm_params = st.norm.fit(_data)
    skewnorm_params = st.skewnorm.fit(_data)
    nct_params = st.nct.fit(
        _data, 5, 0, loc=np.mean(_data), scale=np.std(_data)
    )
    norm_ad = _calculate_anderson_darling(
        _data, lambda x: st.norm.cdf(x, *norm_params)
    )
    skewnorm_ad = _calculate_anderson_darling(
        _data, lambda x: st.skewnorm.cdf(x, *skewnorm_params)
    )
    nct_ad = _calculate_anderson_darling(
        _data, lambda x: st.nct.cdf(x, *nct_params)
    )
    x = np.linspace(_data.min(), _data.max(), 1000)

    def _get_quantiles(q: float) -> float:
        return st.nct.ppf(q, *nct_params)

    return (
        go.Figure(
            [
                go.Histogram(
                    x=_data,
                    histnorm="probability density",
                    nbinsx=200,
                    name="Densité",
                ),
                go.Scatter(
                    x=x,
                    y=st.norm.pdf(x, *norm_params),
                    name=f"Normale (<i>A</i><sup>2</sup> = {norm_ad:.2f})",
                ),
                go.Scatter(
                    x=x,
                    y=st.skewnorm.pdf(x, *skewnorm_params),
                    name=f"Normale asymétrique (<i>A</i><sup>2</sup> = {skewnorm_ad:.2f})",
                ),
                go.Scatter(
                    x=x,
                    y=st.nct.pdf(x, *nct_params),
                    name=f"T non centrée (<i>A</i><sup>2</sup> = {nct_ad:.2f})",
                ),
            ],
            {
                "height": 400,
                "width": 800,
                "margin": {
                    "t": 0,
                    "b": 0,
                    "l": 0,
                    "r": 0,
                    "autoexpand": True,
                },
                "font_family": "Playfair Display",
                "font_size": 18,
                "legend": {
                    "x": 0,
                    "xanchor": "left",
                    "bgcolor": "rgba(0,0,0,0)",
                },
                "xaxis_title": "Pression atmosphérique (kPa)",
                "yaxis_title": "Densité",
            },
        ),
        _get_quantiles,
    )


def create_precipitation_fig(
    data: pl.DataFrame,
) -> go.Figure:
    data = data.group_by(pl.col("datetime").dt.date()).agg(
        pl.col("precipitation").sum()
    )
    _data = data["precipitation"].drop_nulls().to_numpy()
    p_zeros = (_data == 0).mean()
    _data = _data[_data > 0]

    return go.Figure(
        [
            go.Histogram(
                x=_data,
                histnorm="probability density",
                nbinsx=200,
                name="Densité",
            ),
        ],
        {
            "height": 400,
            "width": 800,
            "margin": {
                "t": 0,
                "b": 0,
                "l": 0,
                "r": 0,
                "autoexpand": True,
            },
            "font_family": "Playfair Display",
            "font_size": 18,
            "legend": {
                "x": 1,
                "xanchor": "right",
                "bgcolor": "rgba(0,0,0,0)",
            },
            "xaxis_title": "Précipitation (mm)",
            "yaxis_title": "Densité",
            "annotations": [
                {
                    "showarrow": False,
                    "x": 0.5,
                    "xanchor": "center",
                    "y": 0.5,
                    "xref": "paper",
                    "yref": "paper",
                    "text": f"Proportion de jours avec aucune précipitation = {p_zeros*100:.1f}%",
                }
            ],
        },
    )


def create_temperature_fig(
    data: pl.DataFrame,
) -> go.Figure:
    _data = data["temperature"].drop_nulls().sample(10_000).to_numpy()

    return go.Figure(
        [
            go.Histogram(
                x=_data,
                histnorm="probability density",
                nbinsx=200,
                name="Densité",
            ),
        ],
        {
            "height": 400,
            "width": 800,
            "margin": {
                "t": 0,
                "b": 0,
                "l": 0,
                "r": 0,
                "autoexpand": True,
            },
            "font_family": "Playfair Display",
            "font_size": 18,
            "legend": {
                "x": 1,
                "xanchor": "right",
                "bgcolor": "rgba(0,0,0,0)",
            },
            "xaxis_title": "Température (°C)",
            "yaxis_title": "Densité",
        },
    )


def write_storm_return_periods(data: pl.DataFrame) -> None:
    template_path = templates_dir / "storm_return_periods.typ"
    path = figures_dir / "storm_return_periods.typ"
    body = ",\n    ".join(
        ", ".join(
            [
                f"[{r['period']}]",
                f"[{r['wind_speed']:.2f}]",
                f"[{r['duration']:.2f}]",
            ]
        )
        for r in data.sort("period").to_dicts()
    )
    with open(template_path) as f:
        template = f.read()
    with open(path, "w") as f:
        f.write(template.replace("__body__", body))


def write_diff_return_periods(data: pl.DataFrame) -> None:
    template_path = templates_dir / "diff_return_periods.typ"
    path = figures_dir / "diff_return_periods.typ"
    body = ",\n    ".join(
        ", ".join(
            [
                f"[{r['period']}]",
                f"[{r['diff']:.0f}]",
                f"[{r['R_T']:.2f}]",
            ]
        )
        for r in data.sort("period").to_dicts()
    )
    with open(template_path) as f:
        template = f.read()
    with open(path, "w") as f:
        f.write(template.replace("__body__", body))


def write_pressure_return_periods(data: pl.DataFrame) -> None:
    template_path = templates_dir / "pressure_return_periods.typ"
    path = figures_dir / "pressure_return_periods.typ"
    body = ",\n    ".join(
        ", ".join(
            [
                f"[{r['period']}]",
                f"[{r['pressure']:.0f}]",
            ]
        )
        for r in data.sort("period").to_dicts()
    )
    with open(template_path) as f:
        template = f.read()
    with open(path, "w") as f:
        f.write(template.replace("__body__", body))


def write_wave_params(data: pl.DataFrame, fetch: float) -> None:
    template_path = templates_dir / "wave_params.typ"
    path = figures_dir / "wave_params.typ"
    g = 9.81
    variables = [
        ("F", r"$F$", "[m]", ",.0f"),
        ("U'", r"$U'$", "[m/s]", ".2f"),
        ("t", r"$t$", "[h]", ".2f"),
        ("U", r"$U$", "[m/s]", ".2f"),
        ("F*", r"$F^\*$", "[-]", ",.0f"),
        ("t*", r"$t^\*$", "[-]", ",.0f"),
        ("F_eff*", r"$F_(e f f)^\*$", "[-]", ",.0f"),
        ("H_m0*", r"$H_(m 0)^\*$", "[-]", ".3f"),
        ("T_p*", r"$T_p^\*$", "[-]", ".2f"),
        ("H_m0", r"$H_(m 0)$", "[m]", ".2f"),
        ("T_p", r"$T_p$", "[s]", ".2f"),
    ]
    data = (
        data.select(
            "period",
            pl.col("wind_speed").alias("U'"),
            pl.col("duration").alias("t"),
            pl.col("R_T"),
            pl.lit(fetch).alias("F"),
        )
        .with_columns((pl.col("U'") * pl.col("R_T")).alias("U"))
        .with_columns(
            (pl.col("F") * g / pl.col("U") ** 2).alias("F*"),
            (pl.col("t") * 3600 * g / pl.col("U")).alias("t*"),
        )
        .with_columns(((pl.col("t*") / 68.8) ** (3 / 2)).alias("F_eff*"))
        .with_columns(
            (
                pl.min_horizontal(
                    0.243,
                    0.0016
                    * pl.min_horizontal(pl.col("F*"), pl.col("F_eff*"))
                    ** (1 / 2),
                )
            ).alias("H_m0*"),
            (
                pl.min_horizontal(
                    8.13,
                    0.286
                    * pl.min_horizontal(pl.col("F*"), pl.col("F_eff*"))
                    ** (1 / 3),
                )
            ).alias("T_p*"),
        )
        .with_columns(
            (pl.col("U") ** 2 * pl.col("H_m0*") / g).alias("H_m0"),
            (pl.col("U") * pl.col("T_p*") / g).alias("T_p"),
        )
        .sort("period")
    )
    body = ",\n    ".join(
        [
            (
                f"[*{variable}*], "
                if name in ("H_m0", "T_p")
                else f"[{variable}], "
            )
            + (f"[*{unit}*], " if name in ("H_m0", "T_p") else f"[{unit}], ")
            + ", ".join(
                ("[*{{x:{f}}}*]" if name in ("H_m0", "T_p") else "[{{x:{f}}}]")
                .format(f=format)
                .format(x=r[name])
                .replace(",", " ")
                for r in data.to_dicts()
            )
            for name, variable, unit, format in variables
        ]
    )
    with open(template_path) as f:
        template = f.read()
    with open(path, "w") as f:
        f.write(template.replace("__body__", body))


###########
# private #
###########


def _fit_storms_with_ged(
    data: pl.DataFrame, feature: str, threshold: float
) -> tuple[
    str,
    Callable[[npt.NDArray[np.float64]], npt.NDArray[np.float64]],
]:
    x = data[feature].to_numpy()
    _threshold = np.quantile(x, threshold)
    excess = x[x > _threshold] - _threshold
    params = st.genpareto.fit(excess, floc=0)

    def _get_quantiles(q: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
        return _threshold + st.genpareto.ppf(np.maximum(q, threshold), *params)

    return (
        f"GPD - POT({threshold*100:.0f}%)",
        _get_quantiles,
    )


def _fit_storms_with_exponential(
    data: pl.DataFrame, feature: str, threshold: float
) -> tuple[
    str,
    Callable[[npt.NDArray[np.float64]], npt.NDArray[np.float64]],
]:
    x = data[feature].to_numpy()
    _threshold = np.quantile(x, threshold)
    excess = x[x > _threshold] - _threshold
    params = st.expon.fit(excess, floc=0)

    def _get_quantiles(q: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
        return _threshold + st.expon.ppf(np.maximum(q, threshold), *params)

    return (
        f"Exponentielle - POT({threshold*100:.0f}%)",
        _get_quantiles,
    )


def _fit_storms_with_gev(
    data: pl.DataFrame, feature: str, n_max: float
) -> tuple[
    str,
    Callable[[npt.NDArray[np.float64]], npt.NDArray[np.float64]],
]:
    x = (
        data.group_by(pl.col("datetime_start").dt.year())
        .agg(pl.col(feature).top_k(n_max))[feature]
        .explode()
        .to_numpy()
    )
    params = st.genextreme.fit(x)

    def _get_quantiles(q: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
        return st.genextreme.ppf(q, *params)

    return (
        (
            "GEV - maximum annuel"
            if n_max == 1
            else f"GEV - {n_max} maximum annuels"
        ),
        _get_quantiles,
    )


def _fit_storms_with_gumbel(
    data: pl.DataFrame, feature: str, n_max: float
) -> tuple[
    str,
    Callable[[npt.NDArray[np.float64]], npt.NDArray[np.float64]],
]:
    x = (
        data.group_by(pl.col("datetime_start").dt.year())
        .agg(pl.col(feature).top_k(n_max))[feature]
        .explode()
        .to_numpy()
    )
    params = st.gumbel_r.fit(x)

    def _get_quantiles(q: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
        return st.gumbel_r.ppf(q, *params)

    return (
        (
            "Gumbel - maximum annuel"
            if n_max == 1
            else f"Gumbel - {n_max} maximum annuels"
        ),
        _get_quantiles,
    )


def _fit_storms_with_weibull(
    data: pl.DataFrame, feature: str, n_max: float
) -> tuple[
    str,
    Callable[[npt.NDArray[np.float64]], npt.NDArray[np.float64]],
]:
    x = (
        data.group_by(pl.col("datetime_start").dt.year())
        .agg(pl.col(feature).top_k(n_max))[feature]
        .explode()
        .to_numpy()
    )
    params = st.weibull_min.fit(x)

    def _get_quantiles(q: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
        return st.weibull_min.ppf(q, *params)

    return (
        (
            "Weibull - maximum annuel"
            if n_max == 1
            else f"Weibull- {n_max} maximum annuels"
        ),
        _get_quantiles,
    )


def _fit_storms_with_lognormal(data: pl.DataFrame, feature: str) -> tuple[
    str,
    Callable[[npt.NDArray[np.float64]], npt.NDArray[np.float64]],
]:
    x = data[feature].to_numpy()
    params = st.lognorm.fit(x)

    def _get_quantiles(q: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
        return st.lognorm.ppf(q, *params)

    return (
        "Lognormale",
        _get_quantiles,
    )


def _fit_storms_with_normal(data: pl.DataFrame, feature: str) -> tuple[
    str,
    Callable[[npt.NDArray[np.float64]], npt.NDArray[np.float64]],
]:
    x = data[feature].to_numpy()
    params = st.norm.fit(x)

    def _get_quantiles(q: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
        return st.norm.ppf(q, *params)

    return (
        "Normale",
        _get_quantiles,
    )


def _calculate_qq_rmse(
    x: npt.NDArray[np.float64],
    get_quantiles: Callable[
        [npt.NDArray[np.float64]], npt.NDArray[np.float64]
    ],
    threshold: float | None = None,
) -> float:
    quantiles = np.arange(0.01 if threshold is None else threshold, 1, 0.01)
    y = np.quantile(x, quantiles)
    x = get_quantiles(quantiles)
    return float(np.sqrt(np.mean((y - x) ** 2)))


def _calculate_anderson_darling(
    x: npt.NDArray[np.float64],
    cdf: Callable[[npt.NDArray[np.float64]], npt.NDArray[np.float64]],
) -> float:
    x_sorted = np.sort(x)
    n = len(x_sorted)

    eps = 1e-12
    f = np.clip(cdf(x_sorted), eps, 1.0 - eps)

    i = np.arange(1, n + 1)
    s = (2 * i - 1) * (np.log(f) + np.log(1.0 - f[::-1]))

    return float(-n - np.sum(s) / n)


def _calculate_storm_return_period(
    wind_speed_get_quantiles: Callable[
        [npt.NDArray[np.float64]], npt.NDArray[np.float64]
    ],
    duration_get_quantiles: Callable[
        [npt.NDArray[np.float64]], npt.NDArray[np.float64]
    ],
    return_period: int,
) -> dict[str, float]:
    wind_speed = wind_speed_get_quantiles(np.array([1 - 1 / return_period]))[0]
    duration = duration_get_quantiles(np.array([1 - 1 / return_period]))[0]
    return {
        "period": return_period,
        "wind_speed": wind_speed,
        "duration": duration,
    }
