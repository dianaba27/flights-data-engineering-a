import argparse
import logging
import sys

import awswrangler as wr


DATABASE_BRONZE = "flights_bronze"
DATABASE_SILVER = "flights_silver"


def setup_logger() -> logging.Logger:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s"
    )
    return logging.getLogger(__name__)


def parse_args():
    parser = argparse.ArgumentParser(description="Silver ETL for flights dataset with Athena")
    parser.add_argument("--bucket", required=True, help="Nombre del bucket S3")
    return parser.parse_args()


def run_ctas(sql: str, database: str, logger: logging.Logger, label: str) -> None:
    logger.info("Ejecutando CTAS para %s", label)
    wr.athena.start_query_execution(sql=sql, database=database, wait=True)
    logger.info("CTAS terminado para %s", label)


def main():
    logger = setup_logger()
    args = parse_args()
    bucket = args.bucket

    try:
        logger.info("Iniciando Silver ETL con Athena")
        logger.info("Bucket: %s", bucket)

        wr.catalog.create_database(name=DATABASE_SILVER, exist_ok=True)
        logger.info("Base %s lista en Glue Catalog", DATABASE_SILVER)

        wr.catalog.delete_table_if_exists(database=DATABASE_SILVER, table="flights_daily")
        wr.catalog.delete_table_if_exists(database=DATABASE_SILVER, table="flights_monthly")
        wr.catalog.delete_table_if_exists(database=DATABASE_SILVER, table="flights_by_airport")

        sql_daily = f"""
        CREATE TABLE {DATABASE_SILVER}.flights_daily
        WITH (
            format = 'PARQUET',
            write_compression = 'SNAPPY',
            external_location = 's3://{bucket}/flights/silver/flights_daily/',
            partitioned_by = ARRAY['month']
        ) AS
        SELECT
            year,
            day,
            COUNT(*) AS total_flights,
            SUM(CASE WHEN departure_delay > 0 THEN 1 ELSE 0 END) AS total_delayed,
            SUM(CASE WHEN cancelled = 1 THEN 1 ELSE 0 END) AS total_cancelled,
            AVG(CASE WHEN cancelled = 0 THEN departure_delay END) AS avg_departure_delay,
            AVG(CASE WHEN cancelled = 0 THEN arrival_delay END) AS avg_arrival_delay,
            month
        FROM {DATABASE_BRONZE}.flights
        GROUP BY year, day, month
        """

        sql_monthly = f"""
        CREATE TABLE {DATABASE_SILVER}.flights_monthly
        WITH (
            format = 'PARQUET',
            write_compression = 'SNAPPY',
            external_location = 's3://{bucket}/flights/silver/flights_monthly/'
        ) AS
        SELECT
            month,
            airline,
            COUNT(*) AS total_flights,
            SUM(CASE WHEN arrival_delay > 0 THEN 1 ELSE 0 END) AS total_delayed,
            SUM(CASE WHEN cancelled = 1 THEN 1 ELSE 0 END) AS total_cancelled,
            AVG(CASE WHEN cancelled = 0 THEN arrival_delay END) AS avg_arrival_delay,
            100.0 * AVG(CASE WHEN cancelled = 0 AND arrival_delay <= 15 THEN 1.0 ELSE 0.0 END) AS on_time_pct
        FROM {DATABASE_BRONZE}.flights
        GROUP BY month, airline
        """

        sql_airport = f"""
        CREATE TABLE {DATABASE_SILVER}.flights_by_airport
        WITH (
            format = 'PARQUET',
            write_compression = 'SNAPPY',
            external_location = 's3://{bucket}/flights/silver/flights_by_airport/'
        ) AS
        SELECT
            origin_airport,
            COUNT(*) AS total_departures,
            SUM(CASE WHEN departure_delay > 0 THEN 1 ELSE 0 END) AS total_delayed,
            SUM(CASE WHEN cancelled = 1 THEN 1 ELSE 0 END) AS total_cancelled,
            AVG(CASE WHEN cancelled = 0 THEN departure_delay END) AS avg_departure_delay,
            CASE
                WHEN SUM(CASE WHEN departure_delay > 0 THEN departure_delay ELSE 0 END) > 0
                THEN 100.0 * SUM(COALESCE(weather_delay, 0)) /
                     SUM(CASE WHEN departure_delay > 0 THEN departure_delay ELSE 0 END)
                ELSE 0.0
            END AS pct_weather_delay
        FROM {DATABASE_BRONZE}.flights
        GROUP BY origin_airport
        """

        run_ctas(sql_daily, DATABASE_BRONZE, logger, "flights_daily")
        run_ctas(sql_monthly, DATABASE_BRONZE, logger, "flights_monthly")
        run_ctas(sql_airport, DATABASE_BRONZE, logger, "flights_by_airport")

        logger.info("Silver ETL terminó exitosamente")

    except Exception as e:
        logger.exception("Error en Silver ETL: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()