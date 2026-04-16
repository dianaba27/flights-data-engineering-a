import argparse
import logging
import os
import sys

import awswrangler as wr
import pandas as pd


DATABASE = "flights_bronze"


def setup_logger() -> logging.Logger:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s"
    )
    return logging.getLogger(__name__)


def parse_args():
    parser = argparse.ArgumentParser(description="Bronze ETL for flights dataset")
    parser.add_argument("--bucket", required=True, help="Nombre del bucket S3")
    parser.add_argument("--data-dir", required=True, help="Directorio local donde están los CSVs")
    return parser.parse_args()


def validate_file_exists(path: str) -> None:
    assert os.path.exists(path), f"No existe el archivo: {path}"


def validate_dataframe(df: pd.DataFrame, table_name: str) -> None:
    assert not df.empty, f"El DataFrame de {table_name} está vacío"


def load_small_csv(path: str, table_name: str) -> pd.DataFrame:
    validate_file_exists(path)
    df = pd.read_csv(path)
    validate_dataframe(df, table_name)
    return df


def write_small_table(df: pd.DataFrame, table_name: str, bucket: str, logger: logging.Logger) -> None:
    path = f"s3://{bucket}/flights/bronze/{table_name}/"

    wr.s3.to_parquet(
        df=df,
        path=path,
        dataset=True,
        database=DATABASE,
        table=table_name,
        mode="overwrite"
    )

    logger.info("Bronze/%s cargada con %s filas", table_name, len(df))
    logger.info("Ruta destino: %s", path)


def write_flights_in_chunks(flights_path: str, bucket: str, logger: logging.Logger, chunksize: int = 250_000) -> None:
    validate_file_exists(flights_path)

    path = f"s3://{bucket}/flights/bronze/flights/"
    total_rows = 0

    logger.info("Iniciando carga por chunks de flights.csv")
    logger.info("Chunk size: %s", chunksize)

    for i, chunk in enumerate(pd.read_csv(flights_path, chunksize=chunksize), start=1):
        validate_dataframe(chunk, f"flights_chunk_{i}")

        write_mode = "overwrite" if i == 1 else "append"

        wr.s3.to_parquet(
            df=chunk,
            path=path,
            dataset=True,
            database=DATABASE,
            table="flights",
            mode=write_mode
        )

        total_rows += len(chunk)
        logger.info("Chunk %s cargado con %s filas | acumulado=%s", i, len(chunk), total_rows)

    logger.info("Bronze/flights cargada con %s filas totales", total_rows)
    logger.info("Ruta destino: %s", path)


def main():
    logger = setup_logger()
    args = parse_args()

    try:
        logger.info("Iniciando Bronze ETL")
        logger.info("Bucket: %s", args.bucket)
        logger.info("Data dir: %s", args.data_dir)

        wr.catalog.create_database(name=DATABASE, exist_ok=True)
        logger.info("Base %s lista en Glue Catalog", DATABASE)

        base_dir = os.path.join(args.data_dir, "flights")

        airlines_path = os.path.join(base_dir, "airlines.csv")
        airports_path = os.path.join(base_dir, "airports.csv")
        flights_path = os.path.join(base_dir, "flights.csv")

        airlines_df = load_small_csv(airlines_path, "airlines")
        airports_df = load_small_csv(airports_path, "airports")

        write_small_table(airlines_df, "airlines", args.bucket, logger)
        write_small_table(airports_df, "airports", args.bucket, logger)
        write_flights_in_chunks(flights_path, args.bucket, logger)

        logger.info("Bronze ETL terminó exitosamente")

    except Exception as e:
        logger.exception("Error en Bronze ETL: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()