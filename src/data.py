import asyncio
import functools
import math
import zipfile
from datetime import datetime
from pathlib import Path

import cdsapi
import httpx
import polars as pl
import pyproj
import requests
import xarray as xr

#########
# types #
#########

data_dir = Path(__file__).parent / ".." / "data"

##########
# public #
##########


async def read_weather_data() -> tuple[pl.DataFrame, pl.DataFrame]:
    cpe_loc = (47.366445362339576, -61.87199621249825)
    n_years = 19
    async with httpx.AsyncClient() as client:
        stations = await _read_stations(client)
        stations = _determine_closest_stations(cpe_loc, stations, n=10)
        closest, latest = _select_stations(stations, n_years=n_years)
        closest = await _read_station_data(client, closest)
        latest = await _read_station_data(client, latest)
    return closest, latest


async def read_era5_data(
    start: datetime, end: datetime
) -> tuple[pl.DataFrame, pl.DataFrame]:
    cpe_loc = (47.366445362339576, -61.87199621249825)
    lat, lon = cpe_loc
    lat = round(lat * 4) / 4
    lon = round(lon * 4) / 4
    hourly_data = _read_era5_hourly_data(lat, lon, start, end)
    monthly_data = await _read_era5_monthly_data(lat, lon, start, end)
    return hourly_data, monthly_data


def extract_storms(
    data: pl.DataFrame, *, threshold: float = 15.0
) -> pl.DataFrame:
    return (
        data.with_columns((pl.col("wind_speed") > threshold).alias("in_storm"))
        .with_columns(
            (pl.col("in_storm") != pl.col("in_storm").shift().fill_null(False))
            .cum_sum()
            .alias("storm_id")
        )
        .filter(pl.col("in_storm"))
        .group_by("storm_id")
        .agg(
            pl.col("datetime").min().alias("datetime_start"),
            (pl.col("datetime").max() - pl.col("datetime").min())
            .dt.total_hours()
            .alias("duration"),
            pl.col("wind_direction").min().alias("wind_direction_min"),
            pl.col("wind_direction").max().alias("wind_direction_max"),
            pl.col("wind_speed").mean().alias("wind_speed_mean"),
            pl.col("wind_speed").max().alias("wind_speed_max"),
        )
        .filter(pl.col("duration") >= 1)
    )


def read_fetch() -> pl.DataFrame:
    cpe_loc = (47.366445362339576, -61.87199621249825)
    lat, lon = cpe_loc
    path = data_dir / "raw" / "bathymetry" / "bathymetry.nc"
    zip_path = data_dir / "raw" / "bathymetry.zip"

    if not path.exists():
        with zipfile.ZipFile(zip_path, "r") as f:
            f.extractall(path.parent)
        for _path in path.parent.glob("**/*"):
            if _path.suffix == ".nc":
                _path.rename(path)
            elif _path.is_file():
                _path.unlink()
        for _path in path.parent.glob("*"):
            if _path.is_dir():
                _path.rmdir()

    bathymetry = xr.load_dataset(path)


###########
# private #
###########


async def _read_stations(client: httpx.AsyncClient) -> pl.DataFrame:
    url = "https://api.weather.gc.ca/collections/climate-stations/items?f=json&limit=10000"

    path = data_dir / "raw" / "weather_stations.ipc"

    if path.exists():
        return pl.read_ipc(path)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        resp = await client.get(url)
        resp.raise_for_status()
        json_data = resp.json()
        data = pl.DataFrame(
            [row["properties"] for row in json_data["features"]]
        ).select(
            pl.col("CLIMATE_IDENTIFIER").alias("id"),
            pl.col("STATION_NAME").alias("station_name"),
            pl.col("LATITUDE")
            .map_elements(_convert_degrees_to_decimal, return_dtype=pl.Float64)
            .alias("lat"),
            pl.col("LONGITUDE")
            .map_elements(_convert_degrees_to_decimal, return_dtype=pl.Float64)
            .alias("lon"),
            pl.col("HLY_FIRST_DATE")
            .str.strptime(pl.Datetime, "%Y-%m-%d %H:%M:%S")
            .dt.date()
            .alias("start"),
            pl.col("HLY_LAST_DATE")
            .str.strptime(pl.Date, "%Y-%m-%d %H:%M:%S")
            .alias("end"),
            (pl.col("HAS_HOURLY_DATA") == "Y").alias("has_data"),
        )
        data.write_ipc(path)
        return data


def _determine_closest_stations(
    location: tuple[float, float], stations: pl.DataFrame, *, n: int
) -> pl.DataFrame:
    geod = pyproj.Geod(ellps="WGS84")

    lat, lon = location
    stations = stations.filter(pl.col("has_data"))

    return (
        pl.DataFrame(
            [
                {
                    "id": row["id"],
                    "distance": geod.inv(lon, lat, row["lon"], row["lat"])[2],
                }
                for row in stations.to_dicts()
            ]
        )
        .sort("distance")
        .head(n)
        .join(stations, on="id")
        .sort("distance")
    )


def _select_stations(
    stations: pl.DataFrame, *, n_years: int
) -> tuple[pl.DataFrame, pl.DataFrame]:
    stations = stations.filter(
        (pl.col("end") - pl.col("start")).dt.total_days() >= n_years * 365
    ).sort("distance")
    closest = stations.head(1)
    latest = stations.sort("end", "distance", descending=[True, False]).head(1)
    return closest, latest


async def _read_station_data(
    client: httpx.AsyncClient,
    station: pl.DataFrame,
    *,
    limit: int = 10_000,
) -> pl.DataFrame:
    if station.shape[0] != 1:
        raise ValueError("A single station must be given in the dataframe.")

    properties = {
        "LOCAL_DATE": "datetime",
        "LONGITUDE_DECIMAL_DEGREES": "lon",
        "LATITUDE_DECIMAL_DEGREES": "lat",
        "TEMP": "temperature",
        "DEW_POINT_TEMP": "dew_point",
        "PRECIP_AMOUNT": "precipitation",
        "RELATIVE_HUMIDITY": "humidity",
        "STATION_PRESSURE": "pressure",
        "VISIBILITY": "visibility",
        "WIND_DIRECTION": "wind_direction",
        "WIND_SPEED": "wind_speed",
    }

    id = station[0, "id"]
    distance = station[0, "distance"]

    url = (
        "https://api.weather.gc.ca/collections/climate-hourly/items?f=json"
        + f"&properties={','.join(properties.keys())}"
        + f"&CLIMATE_IDENTIFIER={id}"
    )

    path = data_dir / "raw" / "stations" / f"{id}.ipc"

    if path.exists():
        data = pl.read_ipc(path)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        total_count = await _get_total_count(client, url)
        data = pl.concat(
            await asyncio.gather(
                *[
                    _fetch_station_data(
                        client,
                        url,
                        properties,
                        offset=offset,
                        limit=limit,
                    )
                    for offset in range(0, total_count, limit)
                ]
            ),
            how="vertical_relaxed",
        ).with_columns(pl.lit(distance).alias("distance"))
        data.write_ipc(path)

    return data.with_columns(
        pl.col("wind_speed") * 1000 / 3600  # convert from km/h to m/s
    )


async def _get_total_count(client: httpx.AsyncClient, base_url: str) -> int:
    url = f"{base_url}&limit=1"
    resp = await client.get(url, timeout=60)
    resp.raise_for_status()
    json_data = resp.json()
    return json_data["numberMatched"]


async def _fetch_station_data(
    client: httpx.AsyncClient,
    base_url: str,
    properties: dict[str, str],
    *,
    offset: int,
    limit: int,
) -> pl.DataFrame:
    url = f"{base_url}&limit={limit}&offset={offset}"
    resp = await client.get(url, timeout=60)
    resp.raise_for_status()
    json_data = resp.json()
    return (
        pl.DataFrame(
            [row["properties"] for row in json_data["features"]],
            infer_schema_length=10_000,
        )
        .rename(properties)
        .with_columns(
            pl.col("datetime").str.strptime(pl.Datetime, "%Y-%m-%d %H:%M:%S")
        )
    )


def _convert_degrees_to_decimal(x: float) -> float:
    _x = str(x)
    if _x.startswith("-"):
        sign = -1
        _x = _x[1:]
    else:
        sign = 1
    hours = int(_x[:2])
    minutes = int(_x[2:4])
    seconds = int(_x[4:]) / 1000
    return sign * (hours + minutes / 60 + seconds / 3600)


def _read_era5_hourly_data(
    lat: float, lon: float, start: datetime, end: datetime
) -> pl.DataFrame:
    _start = start.strftime("%Y-%m-%d")
    _end = end.strftime("%Y-%m-%d")
    path = data_dir / "raw" / "era5" / "hourly.ipc"
    zip_path = data_dir / "raw" / "era5" / "hourly.zip"
    if path.exists():
        return pl.read_ipc(path)
    else:
        if not zip_path.exists():
            client = cdsapi.Client()
            client.retrieve(
                "reanalysis-era5-single-levels-timeseries",
                {
                    "variable": [
                        "10m_u_component_of_wind",
                        "10m_v_component_of_wind",
                        "mean_sea_level_pressure",
                        "2m_temperature",
                        "sea_surface_temperature",
                        "total_precipitation",
                    ],
                    "date": [f"{_start}/{_end}"],
                    "location": {"latitude": lat, "longitude": lon},
                    "data_format": "csv",
                },
                zip_path,
            )
        with zipfile.ZipFile(zip_path, "r") as f:
            f.extractall(zip_path.parent)
        _data = [pl.read_csv(path) for path in zip_path.parent.glob("*.csv")]
        data = (
            functools.reduce(
                lambda acc, df: acc.join(
                    df.drop("latitude", "longitude"),
                    on="valid_time",
                ),
                _data[1:],
                _data[0].drop("latitude", "longitude"),
            )
            .select(
                pl.col("valid_time")
                .str.strptime(pl.Datetime, "%Y-%m-%d %H:%M:%S")
                .alias("datetime"),
                pl.col("u10").alias("wind_speed_u"),
                pl.col("v10").alias("wind_speed_v"),
                pl.col("t2m").alias("land_temperature"),
                pl.col("sst").alias("sea_surface_temperature"),
                pl.col("msl").alias("sea_level_pressure"),
                pl.col("tp").alias("precipitation"),
            )
            .with_columns(
                (pl.col("wind_speed_u").pow(2) + pl.col("wind_speed_v").pow(2))
                .sqrt()
                .alias("wind_speed"),
                # wind is converted to be from the north and from where the wind blows
                (
                    (
                        270
                        - pl.arctan2(
                            pl.col("wind_speed_v"),
                            pl.col("wind_speed_u"),
                        )
                        * 180
                        / math.pi
                    )
                    % 360
                ).alias("wind_direction_raw"),
            )
            .with_columns(
                (pl.col("wind_direction_raw") / 10)
                .ceil()
                .alias("wind_direction")
            )
        )
        data.write_ipc(path)
        return data


async def _read_era5_monthly_data(
    lat: float, lon: float, start: datetime, end: datetime
) -> pl.DataFrame:
    path = data_dir / "raw" / "era5" / "monthly.ipc"

    area = [lat + 0.25, lon - 0.25, lat - 0.25, lon + 0.25]

    if path.exists():
        return pl.read_ipc(path)
    else:
        await asyncio.gather(
            *[
                asyncio.to_thread(
                    _download_monthly_era5_monthly_data, area, year, month
                )
                for year in range(start.year, end.year + 1)
                for month in range(
                    1 if year != start.year else start.month,
                    13 if year != end.year else end.month + 1,
                )
            ]
        )

        _data = [
            xr.load_dataset(path).sel(
                latitude=lat, longitude=lon, method="nearest"
            )
            for path in (data_dir / "raw" / "era5").glob("monthly_*.nc")
            if path.stat().st_size > 0
        ]
        data = pl.concat(
            [
                pl.DataFrame(
                    {
                        "datetime": point["valid_time"].values,
                        "sea_ice_cover": point["siconc"].values,
                    }
                )
                for point in _data
            ]
        )
        data.write_ipc(path)
        return data


def _download_monthly_era5_monthly_data(
    area: list[float], year: int, month: int
) -> None:
    path = data_dir / "raw" / "era5" / f"monthly_{year}_{month:02d}.nc"
    path.parent.mkdir(exist_ok=True)
    if not path.exists():
        client = cdsapi.Client()
        try:
            client.retrieve(
                "reanalysis-era5-single-levels-monthly-means",
                {
                    "product_type": ["monthly_averaged_reanalysis"],
                    "variable": ["sea_ice_cover"],
                    "year": [str(year)],
                    "month": [f"{month:02d}"],
                    "time": ["00:00"],
                    "data_format": "netcdf",
                    "download_format": "unarchived",
                    "area": area,
                },
                path,
            )
        except requests.HTTPError:
            path.touch()
