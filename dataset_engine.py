import os
import sys
import glob
import logging
from typing import Dict, Any, List, Optional
import duckdb
import polars as pl
import dotenv

dotenv.load_dotenv()
logger = logging.getLogger("dataset_engine")

class DatasetEngine:
    """
    High-Performance, Zero-Laptop-CPU Remote & Local Dataset Engine.
    Executes vectorized HTTP Range Requests over Cloudflare R2 / S3 via DuckDB httpfs,
    with automatic seamless fallback to local Parquet cache.
    """

    def __init__(
        self,
        bucket_name: Optional[str] = None,
        endpoint_url: Optional[str] = None,
        access_key_id: Optional[str] = None,
        secret_access_key: Optional[str] = None,
        local_data_dir: str = "data"
    ):
        self.bucket = (bucket_name or os.environ.get("R2_BUCKET_NAME", "agent-datasets")).strip("\"'")
        self.endpoint = (endpoint_url or os.environ.get("R2_ENDPOINT_URL", "")).strip("\"'")
        self.key_id = (access_key_id or os.environ.get("R2_ACCESS_KEY_ID", "")).strip("\"'")
        self.secret = (secret_access_key or os.environ.get("R2_SECRET_ACCESS_KEY", "")).strip("\"'")
        self.local_dir = local_data_dir
        os.makedirs(self.local_dir, exist_ok=True)

        self._r2_configured = bool(self.endpoint and self.key_id and self.secret)
        self._r2_live = False
        self._con = None

    def _get_connection(self) -> duckdb.DuckDBPyConnection:
        """Initializes thread-safe in-memory DuckDB connection with httpfs."""
        con = duckdb.connect(database=":memory:")
        try:
            con.execute("INSTALL httpfs; LOAD httpfs;")
        except Exception as e:
            logger.warning(f"Could not load httpfs: {e}")

        # Configure S3 if credentials present
        if self._r2_configured:
            # Strip https:// for DuckDB endpoint
            endpoint_host = self.endpoint.replace("https://", "").replace("http://", "").strip("/")
            try:
                con.execute(f"""
                    CREATE OR REPLACE SECRET r2_secret (
                        TYPE S3,
                        KEY_ID '{self.key_id}',
                        SECRET '{self.secret}',
                        ENDPOINT '{endpoint_host}',
                        URL_STYLE 'path',
                        USE_SSL true
                    );
                """)
            except Exception as e:
                logger.warning(f"Failed to configure DuckDB S3 secret: {e}")
        return con

    def check_r2_status(self) -> Dict[str, Any]:
        """Probes R2 endpoint to check if edge SSL certificate is live."""
        if not self._r2_configured:
            return {"configured": False, "live": False, "reason": "Credentials missing from environment"}

        con = self._get_connection()
        try:
            # Fast test: list objects in bucket
            con.execute(f"SELECT * FROM glob('s3://{self.bucket}/*') LIMIT 1;").fetchall()
            self._r2_live = True
            return {"configured": True, "live": True, "reason": "R2 connection healthy"}
        except Exception as e:
            err_str = str(e)
            self._r2_live = False
            return {
                "configured": True,
                "live": False,
                "reason": "Edge SSL provisioning in progress" if "SSL" in err_str else err_str
            }

    def execute_query(
        self,
        query: str,
        table_path: Optional[str] = None,
        asset: Optional[str] = None,
        year: Optional[int] = None,
        halo_bars: int = 0
    ) -> Dict[str, Any]:
        """
        Executes a vectorized SQL query over Parquet files.
        Tries remote R2 first; falls back cleanly to local data directory if R2 is unavailable.
        """
        con = self._get_connection()
        used_source = "local"
        resolved_path = None

        # Determine target path
        if self._r2_live or (self._r2_configured and self.check_r2_status().get("live")):
            if table_path:
                resolved_path = f"s3://{self.bucket}/{table_path.lstrip('/')}"
            elif asset and year:
                resolved_path = f"s3://{self.bucket}/asset={asset}/year={year}/*.parquet"
            elif asset:
                resolved_path = f"s3://{self.bucket}/asset={asset}/**/*.parquet"
            else:
                resolved_path = f"s3://{self.bucket}/**/*.parquet"
            used_source = "remote_r2"
        else:
            # Local fallback
            if table_path and os.path.exists(os.path.join(self.local_dir, table_path)):
                resolved_path = os.path.join(self.local_dir, table_path).replace("\\", "/")
            elif asset and year:
                resolved_path = f"{self.local_dir}/asset={asset}/year={year}/*.parquet".replace("\\", "/")
            elif asset:
                resolved_path = f"{self.local_dir}/asset={asset}/**/*.parquet".replace("\\", "/")
            else:
                resolved_path = f"{self.local_dir}/**/*.parquet".replace("\\", "/")
            used_source = "local_cache"

        # If placeholder {dataset} exists in query, substitute it
        formatted_query = query.replace("{dataset}", f"read_parquet('{resolved_path}')") if "{dataset}" in query else query

        try:
            df = con.execute(formatted_query).pl()
            return {
                "success": True,
                "source": used_source,
                "resolved_path": resolved_path,
                "row_count": len(df),
                "columns": df.columns,
                "data": df.head(50).to_dicts(),
                "summary": str(df.describe()) if len(df) > 0 else "Empty result"
            }
        except Exception as e:
            err_str = str(e)
            # If remote query failed because no files exist in R2 bucket yet, fallback to local data
            if used_source == "remote_r2" and "No files found that match the pattern" in err_str:
                local_path = None
                if table_path and os.path.exists(os.path.join(self.local_dir, table_path)):
                    local_path = os.path.join(self.local_dir, table_path).replace("\\", "/")
                elif asset and year:
                    local_path = f"{self.local_dir}/asset={asset}/year={year}/*.parquet".replace("\\", "/")
                elif asset:
                    local_path = f"{self.local_dir}/asset={asset}/**/*.parquet".replace("\\", "/")
                else:
                    local_path = f"{self.local_dir}/**/*.parquet".replace("\\", "/")

                try:
                    fallback_query = query.replace("{dataset}", f"read_parquet('{local_path}')") if "{dataset}" in query else query
                    df = con.execute(fallback_query).pl()
                    return {
                        "success": True,
                        "source": "local_fallback",
                        "resolved_path": local_path,
                        "row_count": len(df),
                        "columns": df.columns,
                        "data": df.head(50).to_dicts(),
                        "summary": str(df.describe()) if len(df) > 0 else "Empty result"
                    }
                except Exception as fallback_err:
                    return {
                        "success": False,
                        "source": "remote_and_local_failed",
                        "resolved_path": resolved_path,
                        "error": f"Remote error: {err_str} | Local error: {fallback_err}"
                    }

            return {
                "success": False,
                "source": used_source,
                "resolved_path": resolved_path,
                "error": err_str
            }

    def upload_to_r2(self, local_file: str, remote_key: str) -> bool:
        """Uploads a local file to Cloudflare R2 bucket using boto3."""
        if not self._r2_configured:
            logger.warning("R2 not configured. Cannot upload.")
            return False
        import boto3
        try:
            s3 = boto3.client(
                "s3",
                endpoint_url=self.endpoint,
                aws_access_key_id=self.key_id,
                aws_secret_access_key=self.secret,
                region_name="auto"
            )
            s3.upload_file(local_file, self.bucket, remote_key.lstrip("/"))
            logger.info(f"Successfully uploaded {local_file} to s3://{self.bucket}/{remote_key}")
            return True
        except Exception as e:
            logger.error(f"Failed to upload to R2: {e}")
            return False

    def convert_and_store_local(
        self,
        csv_path: str,
        asset: str,
        year: int,
        timestamp_col: str = "timestamp"
    ) -> str:
        """
        Converts a CSV file to partitioned, ZSTD-compressed Parquet locally.
        Creates path: data/asset={asset}/year={year}/data.parquet
        """
        target_dir = os.path.join(self.local_dir, f"asset={asset}", f"year={year}")
        os.makedirs(target_dir, exist_ok=True)
        target_file = os.path.join(target_dir, "data.parquet")

        df = pl.read_csv(csv_path)
        # Sort chronologically if timestamp exists
        if timestamp_col in df.columns:
            df = df.sort(timestamp_col)
        df.write_parquet(target_file, compression="zstd")
        return target_file

dataset_engine = DatasetEngine()
