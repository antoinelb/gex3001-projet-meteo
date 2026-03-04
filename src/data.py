import asyncio
from datetime import date, timedelta
from pathlib import Path
from typing import cast

import httpx
import polars as pl
import pyproj

#########
# types #
#########

data_dir = Path(__file__).parent / ".." / "data"

##########
# public #
##########


def read_weather_data() -> pl.DataFrame:
    cpe_loc = (47.366445362339576, -61.87199621249825)
    stations = read_stations()
    print(stations)


def read_stations() -> pl.DataFrame:
    url = "https://api.weather.gc.ca/collections/climate-stations/items?f=json&limit=10000"

    path = data_dir / "raw" / "weather_stations.ipc"

    if path.exists():
        return pl.read_ipc(path)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        resp = httpx.get(url)
        data = pl.DataFrame(
            [row["properties"] for row in resp.json()["features"]]
        ).select(
            pl.col("CLIMATE_IDENTIFIER").alias("id"),
            pl.col("STATION_NAME").alias("station_name"),
            pl.col("LATITUDE").alias("lat") / 10**7,
            pl.col("LONGITUDE").alias("lon") / 10**7,
            pl.col("DLY_FIRST_DATE")
            .str.strptime(pl.Datetime, "%Y-%m-%d %H:%M:%S")
            .dt.date()
            .alias("start"),
            pl.col("DLY_LAST_DATE")
            .str.strptime(pl.Date, "%Y-%m-%d %H:%M:%S")
            .alias("end"),
            (pl.col("HAS_NORMALS_DATA") == "Y").alias("has_normals_data"),
        )
        data.write_ipc(path)
        return data


async def read_station_data(
    stations: pl.DataFrame,
    *,
    limit: int = 10000,
    refresh: bool = False,
    echo: bool = True,
    echo_indent: int = 2,
) -> pl.DataFrame:
    properties = {
        "LOCAL_DATE": "date",
        "LONGITUDE_DECIMAL": "lon",
        "LATITUDE_DECIMAL": "lat",
        "TEMP": "temperature",
        "DEW_POINT_TEMP": "dew_point",
        "PRECIP_AMOUNT": "precipitation",
        "RELATIVE_HUMIDITY": "humidity",
        "STATION_PRESSURE": "pressure",
        "VISIBILITY": "visibility",
        "WIND_DIRECTION": "wind_direction",
        "WIND_SPEED": "wind_speed",
    }
    base_url = f"https://api.weather.gc.ca/collections/climate-hourly/items?f=json&limit=10000&properties={','.join(properties.keys())}"
    async with httpx.AsyncClient() as client:
        _data = await asyncio.gather(
            *[
                _read_station_data(
                    client,
                    base_url,
                    row["id"],
                    row["distance"],
                    limit=limit,
                    refresh=refresh,
                )
                for row in stations.to_dicts()
            ]
        )
    return (
        pl.concat(_data)
        .group_by("date")
        .agg(
            (pl.exclude("distance") / pl.col("distance")).sum()
            / (1 / pl.col("distance")).sum(),
            pl.len(),
        )
        .filter(pl.col("len") == stations.shape[0])
        .drop("len")
        .sort("date")
    )


async def read_closest_data(
    hydro_data: pl.DataFrame, *, n: int = 3, refresh: bool = False
) -> pl.DataFrame:
    weather_stations = read_stations()
    closest_stations = _determine_closest_weather_stations(
        hydro_data, weather_stations, n=n
    )
    weather_data = await read_station_data(closest_stations, refresh=refresh)
    return hydro_data.select("date").join(weather_data, on="date").sort("date")


###########
# private #
###########


async def _read_station_data(
    client: httpx.AsyncClient,
    base_url: str,
    id: str,
    distance: float,
    *,
    limit: int,
    refresh: bool = False,
) -> pl.DataFrame:
    base_url = f"{base_url}&CLIMATE_IDENTIFIER={id}"

    path = data_dir / "raw" / "weather" / "stations" / f"{id}.ipc"

    if path.exists() and not refresh:
        return pl.read_ipc(path)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        total_count = await _get_total_count(client, base_url)
        data = pl.concat(
            await asyncio.gather(
                *[
                    _fetch_station_data(
                        client,
                        base_url,
                        offset,
                        limit=limit,
                    )
                    for offset in range(0, total_count, limit)
                ]
            )
        ).with_columns(pl.lit(distance).alias("distance"))
        data.write_ipc(path)
        return data


async def _get_total_count(client: httpx.AsyncClient, base_url: str) -> int:
    url = f"{base_url}&limit=1"
    resp = await client.get(url)
    resp.raise_for_status()
    json_data = resp.json()
    return json_data["numberMatched"]


async def _fetch_station_data(
    client: httpx.AsyncClient, base_url: str, offset: int, *, limit: int
) -> pl.DataFrame:
    url = f"{base_url}&limit={limit}&offset={offset}"
    resp = await client.get(url)
    resp.raise_for_status()
    json_data = resp.json()
    return pl.DataFrame(
        [row["properties"] for row in json_data["features"]]
    ).select(
        pl.col("LOCAL_DATE")
        .str.strptime(pl.Date, "%Y-%m-%d %H:%M:%S")
        .alias("date"),
        pl.col("MEAN_TEMPERATURE").alias("temperature"),
        pl.col("TOTAL_PRECIPITATION").alias("precipitation"),
    )


def _determine_closest_weather_stations(
    hydro_data: pl.DataFrame, weather_stations: pl.DataFrame, *, n: int
) -> pl.DataFrame:
    geod = pyproj.Geod(ellps="WGS84")

    date_start = cast(date, hydro_data["date"].min())
    date_end = cast(date, hydro_data["date"].max())
    lat = hydro_data[0, "lat"]
    lon = hydro_data[0, "lon"]

    weather_stations = weather_stations.filter(
        pl.col("has_normals_data")
        & (pl.col("start") <= date_start)
        & (pl.col("end") >= (date_end - timedelta(days=10)))
    )

    return (
        pl.DataFrame(
            [
                {
                    "id": row["id"],
                    "distance": geod.inv(lon, lat, row["lon"], row["lat"])[2],
                }
                for row in weather_stations.to_dicts()
            ]
        )
        .sort("distance", descending=True)
        .head(n)
    )
