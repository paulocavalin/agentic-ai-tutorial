"""
inventory_server.py — MCP server that wraps a local SQLite inventory database.

This server exposes tools for querying and managing a simple product inventory.
It auto-creates the database with sample data on first run.

Tools exposed:
  - query_products: Search/filter products by name, category, or price range
  - add_product: Add a new product to the inventory
  - update_stock: Update the stock quantity of an existing product
  - get_stats: Get inventory statistics (total products, low stock, by category)

Usage:
    # Run directly (stdio mode — used by MCP clients):
    python mcp_servers/inventory_server.py

    # Or via uv:
    uv run python mcp_servers/inventory_server.py
"""

import sqlite3
from pathlib import Path
from typing import Optional

from mcp.server.fastmcp import FastMCP

# ── Database setup ────────────────────────────────────────────────────────────

DB_PATH = Path(__file__).parent / "inventory.db"


def _get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def _init_db() -> None:
    """Create tables and seed with sample data if the database doesn't exist."""
    if DB_PATH.exists():
        return

    conn = _get_db()
    conn.executescript("""
        CREATE TABLE products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            price REAL NOT NULL,
            stock INTEGER NOT NULL DEFAULT 0,
            description TEXT
        );

        INSERT INTO products (name, category, price, stock, description) VALUES
            ('Wireless Mouse', 'Electronics', 29.99, 150, 'Ergonomic wireless mouse with USB receiver'),
            ('Mechanical Keyboard', 'Electronics', 89.99, 75, 'RGB mechanical keyboard with Cherry MX switches'),
            ('USB-C Hub', 'Electronics', 45.00, 200, '7-in-1 USB-C hub with HDMI and SD card reader'),
            ('Standing Desk', 'Furniture', 399.99, 30, 'Electric height-adjustable standing desk 60x30'),
            ('Monitor Arm', 'Furniture', 79.99, 85, 'Single monitor arm, supports up to 32 inch'),
            ('Webcam HD', 'Electronics', 59.99, 120, '1080p webcam with built-in microphone'),
            ('Desk Lamp', 'Furniture', 34.99, 95, 'LED desk lamp with adjustable brightness'),
            ('Notebook A5', 'Office Supplies', 12.99, 500, 'Hardcover lined notebook, 200 pages'),
            ('Pen Set', 'Office Supplies', 24.99, 300, 'Set of 5 fine-tip gel pens'),
            ('Whiteboard Markers', 'Office Supplies', 8.99, 400, 'Pack of 4 dry-erase markers'),
            ('Laptop Stand', 'Electronics', 49.99, 60, 'Aluminum laptop stand with ventilation'),
            ('Cable Organizer', 'Office Supplies', 15.99, 250, 'Silicone cable management clips, pack of 10');
    """)
    conn.commit()
    conn.close()


# ── MCP Server ────────────────────────────────────────────────────────────────

_init_db()

mcp = FastMCP("Inventory", json_response=True)


@mcp.tool()
def query_products(
    search: Optional[str] = None,
    category: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    low_stock_only: bool = False,
) -> list[dict]:
    """
    Search and filter products in the inventory.

    Args:
        search: Text to search in product name or description (case-insensitive)
        category: Filter by exact category (Electronics, Furniture, Office Supplies)
        min_price: Minimum price filter
        max_price: Maximum price filter
        low_stock_only: If true, only return products with stock < 50
    """
    conn = _get_db()
    query = "SELECT * FROM products WHERE 1=1"
    params: list = []

    if search:
        query += " AND (LOWER(name) LIKE ? OR LOWER(description) LIKE ?)"
        params.extend([f"%{search.lower()}%", f"%{search.lower()}%"])
    if category:
        query += " AND LOWER(category) = ?"
        params.append(category.lower())
    if min_price is not None:
        query += " AND price >= ?"
        params.append(min_price)
    if max_price is not None:
        query += " AND price <= ?"
        params.append(max_price)
    if low_stock_only:
        query += " AND stock < 50"

    query += " ORDER BY name"
    rows = conn.execute(query, params).fetchall()
    conn.close()

    return [dict(row) for row in rows]


@mcp.tool()
def add_product(
    name: str,
    category: str,
    price: float,
    stock: int = 0,
    description: str = "",
) -> dict:
    """
    Add a new product to the inventory.

    Args:
        name: Product name
        category: Product category (e.g., Electronics, Furniture, Office Supplies)
        price: Product price in USD
        stock: Initial stock quantity (default: 0)
        description: Product description
    """
    conn = _get_db()
    cursor = conn.execute(
        "INSERT INTO products (name, category, price, stock, description) VALUES (?, ?, ?, ?, ?)",
        (name, category, price, stock, description),
    )
    conn.commit()
    product_id = cursor.lastrowid
    conn.close()

    return {
        "success": True,
        "product_id": product_id,
        "message": f"Product '{name}' added with ID {product_id}.",
    }


@mcp.tool()
def update_stock(product_id: int, quantity_change: int) -> dict:
    """
    Update stock quantity for a product (positive to add, negative to remove).

    Args:
        product_id: The product ID to update
        quantity_change: Amount to add (positive) or remove (negative) from stock
    """
    conn = _get_db()
    row = conn.execute("SELECT name, stock FROM products WHERE id = ?", (product_id,)).fetchone()

    if not row:
        conn.close()
        return {"success": False, "error": f"Product with ID {product_id} not found."}

    new_stock = row["stock"] + quantity_change
    if new_stock < 0:
        conn.close()
        return {
            "success": False,
            "error": f"Cannot reduce stock below 0. Current stock: {row['stock']}, requested change: {quantity_change}.",
        }

    conn.execute("UPDATE products SET stock = ? WHERE id = ?", (new_stock, product_id))
    conn.commit()
    conn.close()

    return {
        "success": True,
        "product": row["name"],
        "previous_stock": row["stock"],
        "new_stock": new_stock,
        "change": quantity_change,
    }


@mcp.tool()
def get_stats() -> dict:
    """
    Get inventory statistics: total products, total stock value, category breakdown,
    and products with low stock (< 50 units).
    """
    conn = _get_db()

    total = conn.execute("SELECT COUNT(*) as count, SUM(price * stock) as value FROM products").fetchone()

    categories = conn.execute(
        "SELECT category, COUNT(*) as count, SUM(stock) as total_stock FROM products GROUP BY category ORDER BY category"
    ).fetchall()

    low_stock = conn.execute(
        "SELECT name, stock, category FROM products WHERE stock < 50 ORDER BY stock"
    ).fetchall()

    conn.close()

    return {
        "total_products": total["count"],
        "total_inventory_value": round(total["value"] or 0, 2),
        "categories": [dict(row) for row in categories],
        "low_stock_items": [dict(row) for row in low_stock],
    }


if __name__ == "__main__":
    mcp.run(transport="stdio")
