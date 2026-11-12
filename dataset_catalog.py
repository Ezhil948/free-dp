import os
import sys
import json
from typing import Dict, Any, List, Optional
import duckdb

class DatasetCatalogInspector:
    """
    Automated Schema Inspector and Dataset Catalog Generator.
    Inspects Parquet and CSV files in Cloudflare R2 and local cache,
    extracting column types, row counts, date ranges, and sample rows.
    Formats a prompt context so empirical worker agents write 100% accurate DuckDB scripts.
    """

    def __init__(self, local_dir: str = "data/xauusd", r2_prefix: str = "xauusd"):
        self.local_dir = local_dir
        self.r2_prefix = r2_prefix
        self._cached_catalog = None

    def inspect_datasets(self, force_refresh: bool = False) -> Dict[str, Any]:
        """Inspects all datasets and returns detailed schema metadata."""
        if self._cached_catalog and not force_refresh:
            return self._cached_catalog

        con = duckdb.connect(database=":memory:")
        catalog = {}

        if not os.path.exists(self.local_dir):
            return catalog

        # Priority on Parquet, then CSV
        files = sorted(os.listdir(self.local_dir))
        for fname in files:
            if not (fname.endswith(".parquet") or fname.endswith(".csv")):
                continue
            
            fpath = os.path.join(self.local_dir, fname).replace("\\", "/")
            table_key = fname.split(".")[0].lower() + ("_csv" if fname.endswith(".csv") else "")
            ext = "parquet" if fname.endswith(".parquet") else "csv"

            try:
                # 1. Inspect Schema using DESCRIBE
                read_func = f"read_parquet('{fpath}')" if ext == "parquet" else f"read_csv('{fpath}', header=True)"
                schema_df = con.execute(f"DESCRIBE SELECT * FROM {read_func};").df()
                
                columns_meta = []
                for _, row in schema_df.iterrows():
                    columns_meta.append({
                        "name": str(row["column_name"]),
                        "type": str(row["column_type"]),
                        "nullable": bool(row["null"] == "YES")
                    })

                # 2. Get Row Count and Date Range if time column exists
                cols = [c["name"] for c in columns_meta]
                time_col = "time" if "time" in cols else ("timestamp" if "timestamp" in cols else None)

                if time_col:
                    stats = con.execute(f"""
                        SELECT 
                            COUNT(*) as total_rows,
                            MIN({time_col}) as start_time,
                            MAX({time_col}) as end_time
                        FROM {read_func};
                    """).df().to_dict(orient="records")[0]
                else:
                    total_count = con.execute(f"SELECT COUNT(*) as total_rows FROM {read_func};").fetchone()[0]
                    stats = {"total_rows": total_count, "start_time": "N/A", "end_time": "N/A"}

                # 3. Sample 2 Rows
                raw_samples = con.execute(f"SELECT * FROM {read_func} LIMIT 2;").df().to_dict(orient="records")
                sample_rows = []
                for s_row in raw_samples:
                    sample_rows.append({str(k): (str(v) if hasattr(v, "isoformat") or not isinstance(v, (int, float, bool, str)) else v) for k, v in s_row.items()})

                # Infer timeframe
                tf = "Unknown"
                if "m5" in fname.lower():
                    tf = "5-Minute (M5)"
                elif "m15" in fname.lower():
                    tf = "15-Minute (M15)"
                elif "m30" in fname.lower():
                    tf = "30-Minute (M30)"
                elif "h1" in fname.lower():
                    tf = "1-Hour (H1)"

                start_str = str(stats.get("start_time")) if stats.get("start_time") is not None else "N/A"
                end_str = str(stats.get("end_time")) if stats.get("end_time") is not None else "N/A"

                catalog[fname] = {
                    "filename": fname,
                    "table_identifier": table_key,
                    "format": ext.upper(),
                    "timeframe": tf,
                    "local_path": fpath,
                    "r2_path": f"s3://agent-datasets/{self.r2_prefix}/{fname}",
                    "row_count": int(stats["total_rows"]),
                    "total_rows": int(stats["total_rows"]),
                    "date_range": f"{start_str} → {end_str}",
                    "columns": columns_meta,
                    "sample_rows": sample_rows
                }

            except Exception as e:
                print(f"[Dataset Catalog Warning] Error inspecting {fname}: {e}")

        self._cached_catalog = catalog
        return catalog

    def get_schema_dict(self, dataset_keyword: str = "") -> Dict[str, str]:
        """
        Returns a {col_name: col_type} mapping for the dataset matching ``dataset_keyword``.

        Returns an empty mapping when no dataset matches. Never silently falls back to the
        first available table: doing so injects Gold/XAUUSD columns into unrelated domains.
        """
        if not dataset_keyword or not dataset_keyword.strip():
            return {}
        catalog = self.inspect_datasets()
        if not catalog:
            return {}
        keyword = dataset_keyword.strip().lower()
        target = None
        for k, meta in catalog.items():
            searchable = f"{k} {meta.get('table_identifier', '')}".lower()
            if keyword in searchable:
                target = meta
                break
        if not target or "columns" not in target:
            return {}
        return {c["name"]: c["type"] for c in target["columns"]}

    def format_catalog_for_prompt(self, preferred_format: str = "PARQUET") -> str:
        """
        Formats an exhaustive markdown data catalog ready for injection
        into worker agent prompts so they write 100% accurate DuckDB scripts.
        """
        catalog = self.inspect_datasets()
        if not catalog:
            return "No datasets currently registered in catalog."

        lines = [
            "### 📊 AVAILABLE REAL-WORLD DATASETS & DUCKDB SCHEMA CATALOG",
            "You have direct, authorized access to query real historical market data via DuckDB in your Python test script.",
            "Use the EXACT column names and file paths specified below:\n"
        ]

        # Prioritize parquet if preferred
        sorted_keys = sorted(
            catalog.keys(),
            key=lambda k: (0 if catalog[k]["format"] == preferred_format else 1, k)
        )

        for k in sorted_keys:
            d = catalog[k]
            # Skip CSV duplicates if Parquet exists unless requested
            if preferred_format == "PARQUET" and d["format"] == "CSV" and k.replace(".csv", ".parquet") in catalog:
                continue

            lines.append(f"#### DATASET: `{d['filename']}` ({d['timeframe']})")
            lines.append(f"- **File Path (Local)**: `'{d['local_path']}'`")
            row_count = d.get("total_rows", d.get("row_count", 0))
            lines.append(f"- **Total Rows / Bars**: {row_count:,}")
            lines.append(f"- **Date Range**: {d['date_range']}")
            lines.append("- **Columns & Data Types**:")
            for col in d["columns"]:
                note = ""
                name = col["name"].lower()
                if name == "time":
                    note = " (Timestamp of bar open, UTC)"
                elif name in ["open", "high", "low", "close"]:
                    note = f" (Bar {name} price in USD)"
                elif name == "tick_volume":
                    note = " (Tick arrival count per bar)"
                elif name == "spread":
                    note = " (Broker spread in points, e.g. 21 = 0.21 USD)"
                lines.append(f"  * `{col['name']}`: {col['type']}{note}")

            if d.get("sample_rows"):
                lines.append("- **Sample First Row**:")
                clean_sample = {k: (str(v) if not isinstance(v, (int, float, bool)) else v) for k, v in d["sample_rows"][0].items()}
                lines.append(f"  `{json.dumps(clean_sample)}`")
            lines.append("")

        lines.append("### 🛠️ REQUIRED DUCKDB EXECUTION TEMPLATE IN SCRIPT:")
        lines.append("In your ```python ... ``` block, execute your query directly on the parquet/csv file using DuckDB:")
        lines.append("```python")
        lines.append("import duckdb")
        lines.append("import json")
        lines.append("")
        lines.append("con = duckdb.connect()")
        lines.append("# Zero-copy query directly over millions of rows:")
        lines.append("query = '''")
        lines.append("    SELECT ")
        lines.append("        AVG(spread) as mean_spread,")
        lines.append("        PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY (high - low)) as p95_volatility,")
        lines.append("        CORR(spread, tick_volume) as spread_volume_corr")
        lines.append("    FROM 'data/xauusd/XAUUSD_M15.parquet'")
        lines.append("    WHERE time >= '2023-01-01'")
        lines.append("'''")
        lines.append("df = con.execute(query).df()")
        lines.append("print(df.to_json(orient='records', indent=2))")
        lines.append("```\n")

        return "\n".join(lines)

dataset_catalog = DatasetCatalogInspector()

if __name__ == "__main__":
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    print(dataset_catalog.format_catalog_for_prompt())
