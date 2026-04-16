import argparse
import json
import logging
import sys
from typing import Optional

import boto3
import pandas as pd
from sqlalchemy import Float, ForeignKey, Integer, String, create_engine, insert, text
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column


def setup_logger() -> logging.Logger:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )
    return logging.getLogger(__name__)


def parse_args():
    parser = argparse.ArgumentParser(description="Create and load PostgreSQL tables for flights dataset")
    parser.add_argument("--rds-endpoint", required=True, help="Primary RDS endpoint")
    parser.add_argument("--secret-name", required=True, help="Secrets Manager secret name")
    parser.add_argument("--data-dir", required=True, help="Local data directory, e.g. data/")
    parser.add_argument("--region", default="us-east-1", help="AWS region for Secrets Manager")
    parser.add_argument("--db-name", default="flights", help="Database name")
    parser.add_argument("--flights-nrows", type=int, default=500000, help="Rows of flights.csv to load")
    return parser.parse_args()


def get_db_credentials(secret_name: str, region: str) -> dict:
    client = boto3.client("secretsmanager", region_name=region)
    secret = client.get_secret_value(SecretId=secret_name)
    creds = json.loads(secret["SecretString"])
    return creds


class Base(DeclarativeBase):
    pass


class Airline(Base):
    __tablename__ = "airlines"

    iata_code: Mapped[str] = mapped_column(String(10), primary_key=True)
    airline: Mapped[Optional[str]] = mapped_column(String(255))


class Airport(Base):
    __tablename__ = "airports"

    iata_code: Mapped[str] = mapped_column(String(10), primary_key=True)
    airport: Mapped[Optional[str]] = mapped_column(String(255))
    city: Mapped[Optional[str]] = mapped_column(String(255))
    state: Mapped[Optional[str]] = mapped_column(String(50))
    country: Mapped[Optional[str]] = mapped_column(String(50))
    latitude: Mapped[Optional[float]] = mapped_column(Float)
    longitude: Mapped[Optional[float]] = mapped_column(Float)


class Flight(Base):
    __tablename__ = "flights"

    flight_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    year: Mapped[Optional[int]] = mapped_column(Integer)
    month: Mapped[Optional[int]] = mapped_column(Integer)
    day: Mapped[Optional[int]] = mapped_column(Integer)
    day_of_week: Mapped[Optional[int]] = mapped_column(Integer)

    airline: Mapped[Optional[str]] = mapped_column(String(10), ForeignKey("airlines.iata_code"))
    flight_number: Mapped[Optional[int]] = mapped_column(Integer)
    tail_number: Mapped[Optional[str]] = mapped_column(String(20))

    origin_airport: Mapped[Optional[str]] = mapped_column(String(10), ForeignKey("airports.iata_code"))
    destination_airport: Mapped[Optional[str]] = mapped_column(String(10), ForeignKey("airports.iata_code"))

    scheduled_departure: Mapped[Optional[int]] = mapped_column(Integer)
    departure_time: Mapped[Optional[float]] = mapped_column(Float)
    departure_delay: Mapped[Optional[float]] = mapped_column(Float)
    taxi_out: Mapped[Optional[float]] = mapped_column(Float)
    wheels_off: Mapped[Optional[float]] = mapped_column(Float)
    scheduled_time: Mapped[Optional[float]] = mapped_column(Float)
    elapsed_time: Mapped[Optional[float]] = mapped_column(Float)
    air_time: Mapped[Optional[float]] = mapped_column(Float)
    distance: Mapped[Optional[float]] = mapped_column(Float)
    wheels_on: Mapped[Optional[float]] = mapped_column(Float)
    taxi_in: Mapped[Optional[float]] = mapped_column(Float)
    scheduled_arrival: Mapped[Optional[int]] = mapped_column(Integer)
    arrival_time: Mapped[Optional[float]] = mapped_column(Float)
    arrival_delay: Mapped[Optional[float]] = mapped_column(Float)
    diverted: Mapped[Optional[int]] = mapped_column(Integer)
    cancelled: Mapped[Optional[int]] = mapped_column(Integer)
    cancellation_reason: Mapped[Optional[str]] = mapped_column(String(5))
    air_system_delay: Mapped[Optional[float]] = mapped_column(Float)
    security_delay: Mapped[Optional[float]] = mapped_column(Float)
    airline_delay: Mapped[Optional[float]] = mapped_column(Float)
    late_aircraft_delay: Mapped[Optional[float]] = mapped_column(Float)
    weather_delay: Mapped[Optional[float]] = mapped_column(Float)


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = [c.strip().lower() for c in df.columns]
    return df


def records_from_df(df: pd.DataFrame) -> list[dict]:
    return [
        {k: None if pd.isnull(v) else v for k, v in row.items()}
        for row in df.to_dict(orient="records")
    ]


def load_airlines(session: Session, path: str, logger: logging.Logger) -> None:
    df = pd.read_csv(path)
    df = normalize_columns(df)

    expected = {"iata_code", "airline"}
    assert expected.issubset(df.columns), f"airlines.csv no tiene columnas esperadas: {expected}"
    assert len(df) > 0, "airlines.csv está vacío"

    records = records_from_df(df[["iata_code", "airline"]])
    session.execute(insert(Airline), records)
    logger.info("airlines cargada con %s filas", len(records))


def load_airports(session: Session, path: str, logger: logging.Logger) -> None:
    df = pd.read_csv(path)
    df = normalize_columns(df)

    expected = {"iata_code", "airport", "city", "state", "country", "latitude", "longitude"}
    assert expected.issubset(df.columns), f"airports.csv no tiene columnas esperadas: {expected}"
    assert len(df) > 0, "airports.csv está vacío"

    records = records_from_df(df[["iata_code", "airport", "city", "state", "country", "latitude", "longitude"]])
    session.execute(insert(Airport), records)
    logger.info("airports cargada con %s filas", len(records))


def load_flights(session: Session, path: str, nrows: int, logger: logging.Logger) -> None:
    df = pd.read_csv(path, nrows=nrows)
    df = normalize_columns(df)

    expected = {
        "year", "month", "day", "day_of_week", "airline", "flight_number", "tail_number",
        "origin_airport", "destination_airport", "scheduled_departure", "departure_time",
        "departure_delay", "taxi_out", "wheels_off", "scheduled_time", "elapsed_time",
        "air_time", "distance", "wheels_on", "taxi_in", "scheduled_arrival", "arrival_time",
        "arrival_delay", "diverted", "cancelled", "cancellation_reason", "air_system_delay",
        "security_delay", "airline_delay", "late_aircraft_delay", "weather_delay"
    }
    assert expected.issubset(df.columns), f"flights.csv no tiene columnas esperadas: faltan {expected - set(df.columns)}"
    assert len(df) > 0, "flights.csv está vacío"

    cols = [
        "year", "month", "day", "day_of_week", "airline", "flight_number", "tail_number",
        "origin_airport", "destination_airport", "scheduled_departure", "departure_time",
        "departure_delay", "taxi_out", "wheels_off", "scheduled_time", "elapsed_time",
        "air_time", "distance", "wheels_on", "taxi_in", "scheduled_arrival", "arrival_time",
        "arrival_delay", "diverted", "cancelled", "cancellation_reason", "air_system_delay",
        "security_delay", "airline_delay", "late_aircraft_delay", "weather_delay"
    ]

    records = records_from_df(df[cols])
    session.execute(insert(Flight), records)
    logger.info("flights cargada con %s filas", len(records))


def main():
    logger = setup_logger()
    args = parse_args()

    try:
        logger.info("Recuperando credenciales desde Secrets Manager")
        creds = get_db_credentials(args.secret_name, args.region)

        db_user = creds["username"]
        db_password = creds["password"]
        db_port = creds.get("port", 5432)
        db_name = args.db_name

        logger.info("Creando engine SQLAlchemy hacia RDS primario")
        engine = create_engine(
            f"postgresql+psycopg2://{db_user}:{db_password}@{args.rds_endpoint}:{db_port}/{db_name}"
        )

        logger.info("Probando conexión")
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("Conexión exitosa a PostgreSQL")

        logger.info("Recreando tablas")
        Base.metadata.drop_all(engine)
        Base.metadata.create_all(engine)
        logger.info("Tablas creadas correctamente")

        base_dir = f"{args.data_dir.rstrip('/')}/flights"
        airlines_path = f"{base_dir}/airlines.csv"
        airports_path = f"{base_dir}/airports.csv"
        flights_path = f"{base_dir}/flights.csv"

        with Session(engine) as session:
            load_airlines(session, airlines_path, logger)
            load_airports(session, airports_path, logger)
            load_flights(session, flights_path, args.flights_nrows, logger)
            session.commit()
            logger.info("Carga completada y commit realizado")

        logger.info("Proceso PostgreSQL terminó exitosamente")

    except Exception as e:
        logger.exception("Error en postgres_load.py: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()