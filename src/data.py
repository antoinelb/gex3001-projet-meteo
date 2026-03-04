import asyncio
from datetime import timedelta
from pathlib import Path

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


async def read_weather_data() -> tuple[pl.DataFrame, pl.DataFrame]:
    cpe_loc = (47.366445362339576, -61.87199621249825)
    n_years = 19
    async with httpx.AsyncClient() as client:
        stations = await _read_stations(client)
        stations = _determine_closest_stations(cpe_loc, stations, n=10)
        closest, latest = _select_stations(stations, n_years=n_years)
        closest = await _read_station_data(client, closest, n_years=n_years)
        latest = await _read_station_data(client, latest, n_years=n_years)
    return closest, latest


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
            pl.col("LATITUDE").alias("lat") / 10**7,
            pl.col("LONGITUDE").alias("lon") / 10**7,
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
    n_years: int,
    limit: int = 10_000,
) -> pl.DataFrame:
    if station.shape[0] != 1:
        raise ValueError("A single station must be given in the dataframe.")

    properties = {
        "LOCAL_DATE": "date",
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
    min_date = (station[0, "end"] - timedelta(days=n_years * 365)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )

    url = (
        "https://api.weather.gc.ca/collections/climate-hourly/items?f=json"
        + f"&properties={','.join(properties.keys())}"
        + f"&CLIMATE_IDENTIFIER={id}"
        + f"&datetime={min_date}/.."
    )

    path = data_dir / "raw" / "stations" / f"{id}.ipc"

    if path.exists():
        return pl.read_ipc(path)
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
            )
        ).with_columns(pl.lit(distance).alias("distance"))
        data.write_ipc(path)
        return data


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
            pl.col("date").str.strptime(pl.Date, "%Y-%m-%d %H:%M:%S")
        )
    )
