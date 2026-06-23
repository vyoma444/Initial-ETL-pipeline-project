#!/usr/bin/env python3
# etl_pipeline.py — Week 5 hands-on project

import pandas as pd
import sqlite3
from datetime import datetime

# ============================================================
# EXTRACT — load raw CSV
# ============================================================
def extract(filepath: str) -> pd.DataFrame:
    df = pd.read_csv(filepath, encoding='latin-1')
    print(f"Extracted {len(df):,} rows from {filepath}")
    return df

# ============================================================
# TRANSFORM — clean and reshape into star schema tables
# ============================================================
def transform(df: pd.DataFrame) -> dict:

    # --- Fix data types ---
    df['Order Date'] = pd.to_datetime(df['Order Date'])
    df['Sales'] = pd.to_numeric(df['Sales'], errors='coerce')
    df['Quantity'] = pd.to_numeric(df['Quantity'], errors='coerce')
    df['Profit'] = pd.to_numeric(df['Profit'], errors='coerce')

    # --- Drop rows with null Sales ---
    df = df.dropna(subset=['Sales'])

    # ========================================================
    # Data Quality Check
    # ========================================================
    negative_sales = df[df['Sales'] < 0]

    if len(negative_sales) > 0:
        print(
            f"WARNING: Found {len(negative_sales)} rows with negative revenue!"
        )
    else:
        print(
            "Data Quality Check Passed: No negative revenue values found."
        )

    # ========================================================
    # Build dim_date
    # ========================================================
    dates = df['Order Date'].drop_duplicates().reset_index(drop=True)

    dim_date = pd.DataFrame({
        'date_key': dates.dt.strftime('%Y%m%d').astype(int),
        'full_date': dates.dt.strftime('%Y-%m-%d'),
        'day_name': dates.dt.day_name(),
        'month_num': dates.dt.month,
        'month_name': dates.dt.month_name(),
        'quarter': dates.dt.quarter,
        'year': dates.dt.year,
        'is_weekend': dates.dt.dayofweek >= 5
    })

    # ========================================================
    # Build dim_product
    # ========================================================
    dim_product = (
        df[['Product ID', 'Product Name',
            'Category', 'Sub-Category']]
        .drop_duplicates(subset='Product ID')
        .reset_index(drop=True)
    )

    dim_product['product_key'] = dim_product.index + 1

    dim_product = dim_product.rename(columns={
        'Product ID': 'product_id',
        'Product Name': 'product_name',
        'Category': 'category',
        'Sub-Category': 'subcategory'
    })

    # ========================================================
    # Build dim_customer
    # ========================================================
    dim_customer = (
        df[['Customer ID', 'Customer Name',
            'Segment', 'City', 'Country']]
        .drop_duplicates(subset='Customer ID')
        .reset_index(drop=True)
    )

    dim_customer['customer_key'] = dim_customer.index + 1

    dim_customer = dim_customer.rename(columns={
        'Customer ID': 'customer_id',
        'Customer Name': 'full_name',
        'Segment': 'segment',
        'City': 'city',
        'Country': 'country'
    })

    # ========================================================
    # Build fact_sales
    # ========================================================
    df2 = df.merge(
        dim_product[['product_id', 'product_key']],
        left_on='Product ID',
        right_on='product_id',
        how='left'
    )

    df2 = df2.merge(
        dim_customer[['customer_id', 'customer_key']],
        left_on='Customer ID',
        right_on='customer_id',
        how='left'
    )

    df2['date_key'] = (
        df2['Order Date']
        .dt.strftime('%Y%m%d')
        .astype(int)
    )

    fact_sales = df2[
        [
            'date_key',
            'product_key',
            'customer_key',
            'Quantity',
            'Sales',
            'Profit'
        ]
    ].rename(columns={
        'Quantity': 'quantity_sold',
        'Sales': 'revenue',
        'Profit': 'profit'
    })

    return {
        'dim_date': dim_date,
        'dim_product': dim_product,
        'dim_customer': dim_customer,
        'fact_sales': fact_sales
    }

# ============================================================
# LOAD — write tables to SQLite warehouse
# ============================================================
def load(tables: dict, db_path: str):

    conn = sqlite3.connect(db_path)

    for name, df in tables.items():
        df.to_sql(
            name,
            conn,
            if_exists='replace',
            index=False
        )

        print(
            f"  Loaded {len(df):,} rows → {name}"
        )

    conn.close()

    print(f"ETL complete → {db_path}")

# ============================================================
# VERIFY — sanity check after loading
# ============================================================
def verify(db_path):

    conn = sqlite3.connect(db_path)

    query = """
    SELECT
        p.category,
        ROUND(SUM(f.revenue), 2) AS total_revenue
    FROM fact_sales f
    JOIN dim_product p
        ON f.product_key = p.product_key
    GROUP BY p.category
    ORDER BY total_revenue DESC;
    """

    result = pd.read_sql_query(query, conn)

    print("\n=== Total Revenue by Category ===")
    print(result)

    conn.close()

# ============================================================
# RUN
# ============================================================
if __name__ == "__main__":

    raw = extract("superstore.csv")

    tables = transform(raw)

    db_file = "warehouse.db"

    load(tables, db_file)

    verify(db_file)