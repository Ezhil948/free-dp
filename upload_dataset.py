import os
import sys
import shutil
import argparse
import polars as pl
import duckdb
import dotenv
from dataset_catalog import dataset_catalog

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

dotenv.load_dotenv()


def upload_dataset(
    file_path: str,
    asset: str = "xauusd",
    convert_parquet: bool = True,
    upload_r2: bool = True
):
    """
    Ingests and registers a dataset for the Council Engine:
    1. Validates and converts CSV to compressed Parquet (ZSTD).
    2. Copies to local workspace cache under `data/<asset>/`.
    3. Uploads to Cloudflare R2 bucket `s3://<bucket>/<asset>/` if R2 credentials exist.
    4. Automatically refreshes `dataset_catalog` so worker agents immediately see the new columns & sample rows.
    """
    if not os.path.exists(file_path):
        print(f"[Dataset Ingest Error] File not found: {file_path}")
        return False

    abs_src = os.path.abspath(file_path)
    base_name = os.path.basename(abs_src)
    clean_asset = asset.lower().strip()
    target_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", clean_asset)
    os.makedirs(target_dir, exist_ok=True)

    files_to_sync = [abs_src]

    # 1. Convert CSV to Parquet if requested
    if convert_parquet and abs_src.lower().endswith(".csv"):
        parquet_name = os.path.splitext(base_name)[0] + ".parquet"
        local_parquet_path = os.path.join(target_dir, parquet_name)
        print(f"[Dataset Ingest] Converting {base_name} -> {parquet_name} via Polars (ZSTD)...")
        try:
            df = pl.read_csv(abs_src)
            df.write_parquet(local_parquet_path, compression="zstd")
            file_mb = round(os.path.getsize(local_parquet_path) / (1024 * 1024), 2)
            print(f"✓ Created optimized Parquet: {parquet_name} ({file_mb} MB, {len(df):,} rows)")
            files_to_sync.append(local_parquet_path)
        except Exception as e:
            print(f"[Warning] Polars conversion failed: {e}. Keeping raw file.")

    # 2. Copy source file into local workspace cache
    dest_path = os.path.join(target_dir, base_name)
    if os.path.abspath(dest_path) != abs_src:
        shutil.copy2(abs_src, dest_path)
        print(f"✓ Cached in local engine repository: data/{clean_asset}/{base_name}")

    # 3. Optional Upload to Cloudflare R2
    bucket_name = os.environ.get("R2_BUCKET_NAME", "agent-datasets").strip("\"'")
    endpoint_url = os.environ.get("R2_ENDPOINT_URL", "").strip("\"'")
    access_key_id = os.environ.get("R2_ACCESS_KEY_ID", "").strip("\"'")
    secret_access_key = os.environ.get("R2_SECRET_ACCESS_KEY", "").strip("\"'")

    r2_ready = bool(endpoint_url and access_key_id and secret_access_key)
    if upload_r2 and r2_ready:
        try:
            import boto3
            s3 = boto3.client(
                "s3",
                endpoint_url=endpoint_url,
                aws_access_key_id=access_key_id,
                aws_secret_access_key=secret_access_key,
                region_name="auto"
            )
            for fpath in files_to_sync:
                fname = os.path.basename(fpath)
                remote_key = f"{clean_asset}/{fname}"
                print(f"Uploading to R2: s3://{bucket_name}/{remote_key}...")
                s3.upload_file(fpath, bucket_name, remote_key)
                print(f"✓ Remote R2 synced: s3://{bucket_name}/{remote_key}")
        except Exception as re:
            print(f"[Warning] Cloudflare R2 upload skipped/failed ({re}). Local cache is active.")
    elif upload_r2 and not r2_ready:
        print("[Notice] R2 credentials not configured in .env. Dataset is available locally.")

    # 4. Refresh and display new schema from dataset_catalog
    dataset_catalog.local_dir = f"data/{clean_asset}"
    dataset_catalog.r2_prefix = clean_asset
    catalog = dataset_catalog.inspect_datasets(force_refresh=True)

    print("\n--- Current Registered Datasets in Catalog ---")
    for tbl, meta in catalog.items():
        print(f"• Table: `{tbl}` | Format: {meta['format']} | Rows: {meta['row_count']:,} | Date: {meta['date_range']}")

    return True


def main():
    parser = argparse.ArgumentParser(description="Upload, convert and register datasets for the Multi-Agent Council Engine")
    parser.add_argument("file", type=str, help="Path to CSV or Parquet file to upload")
    parser.add_argument("--asset", type=str, default="xauusd", help="Asset symbol or domain subfolder (default: xauusd)")
    parser.add_argument("--no-parquet", action="store_true", help="Do not automatically generate compressed .parquet from .csv")
    parser.add_argument("--no-r2", action="store_true", help="Skip uploading to Cloudflare R2 remote bucket")
    args = parser.parse_args()

    upload_dataset(
        file_path=args.file,
        asset=args.asset,
        convert_parquet=not args.no_parquet,
        upload_r2=not args.no_r2
    )


if __name__ == "__main__":
    main()

