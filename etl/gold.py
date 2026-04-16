import argparse
import logging
import sys

import awswrangler as wr


DATABASE_GOLD = "flights_gold"
TABLE_GOLD = "vuelos_analitica"


def setup_logger() -> logging.Logger:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s"
    )
    return logging.getLogger(__name__)


def parse_args():
    parser = argparse.ArgumentParser(description="Gold ETL for flights dataset with Athena CTAS")
    parser.add_argument("--bucket", required=True, help="Nombre del bucket S3")
    return parser.parse_args()


def main():
    logger = setup_logger()
    args = parse_args()
    bucket = args.bucket

    try:
        logger.info("Iniciando Gold ETL con Athena")
        logger.info("Bucket: %s", bucket)

        wr.catalog.create_database(name=DATABASE_GOLD, exist_ok=True)
        logger.info("Base %s lista en Glue Catalog", DATABASE_GOLD)

        wr.catalog.delete_table_if_exists(database=DATABASE_GOLD, table=TABLE_GOLD)
        logger.info("Tabla %s.%s eliminada si existía", DATABASE_GOLD, TABLE_GOLD)

        sql = f"""
        CREATE TABLE {DATABASE_GOLD}.{TABLE_GOLD}
        WITH (
            format = 'PARQUET',
            write_compression = 'SNAPPY',
            external_location = 's3://{bucket}/flights/gold/{TABLE_GOLD}/'
        ) AS
        SELECT
            f.year,
            f.month,
            f.day,
            f.origin_airport,
            ap_orig.airport AS origin_airport_name,
            ap_orig.city AS origin_city,
            ap_orig.state AS origin_state,
            f.destination_airport,
            ap_dest.airport AS destination_airport_name,
            ap_dest.city AS destination_city,
            ap_dest.state AS destination_state,
            f.airline,
            al.airline AS airline_name,
            f.departure_delay,
            f.arrival_delay,
            f.cancelled,
            f.cancellation_reason,
            f.distance,
            f.air_system_delay,
            f.airline_delay,
            f.weather_delay,
            f.late_aircraft_delay,
            f.security_delay
        FROM flights_bronze.flights f
        LEFT JOIN flights_bronze.airlines al
            ON f.airline = al.iata_code
        LEFT JOIN flights_bronze.airports ap_orig
            ON f.origin_airport = ap_orig.iata_code
        LEFT JOIN flights_bronze.airports ap_dest
            ON f.destination_airport = ap_dest.iata_code
        """

        logger.info("Ejecutando CTAS de Gold")
        wr.athena.start_query_execution(
            sql=sql,
            database="flights_bronze",
            wait=True
        )

        logger.info("Gold ETL terminó exitosamente")

    except Exception as e:
        logger.exception("Error en Gold ETL: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()