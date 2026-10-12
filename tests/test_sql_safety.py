from core.sql_agent import UnsafeSQLError, clean_sql, validate_sql


def _blocked(sql):
    try:
        validate_sql(sql)
    except UnsafeSQLError:
        return True
    return False


def test_allows_select_and_cte():
    assert validate_sql("SELECT region, SUM(total_revenue) FROM revenue GROUP BY region")
    assert validate_sql("WITH x AS (SELECT 1 AS a) SELECT a FROM x")


def test_strips_markdown_fences_and_semicolon():
    assert clean_sql("```sql\nSELECT 1;\n```") == "SELECT 1"


def test_blocks_writes_and_ddl():
    for sql in ["DELETE FROM orders", "DROP TABLE customers", "UPDATE orders SET revenue = 0",
                "INSERT INTO orders VALUES (1)", "TRUNCATE refunds", "ALTER TABLE x ADD y int"]:
        assert _blocked(sql), sql


def test_blocks_stacked_statements():
    assert _blocked("SELECT 1; DROP TABLE orders")


def test_blocks_write_hidden_in_cte():
    assert _blocked("WITH d AS (DELETE FROM orders RETURNING *) SELECT * FROM d")


def test_blocks_internal_tables():
    assert _blocked("SELECT * FROM execution_logs")
    assert _blocked("SELECT content FROM documents")


def test_does_not_block_column_names_containing_keywords():
    # created_at contains 'create', updated_at would contain 'update'
    assert validate_sql("SELECT created_at FROM support_tickets")


def test_complete_week_range_trims_partial_weeks():
    import datetime
    from core.sql_agent import complete_week_range
    # data runs Saturday 2025-03-01 to Saturday 2025-05-31
    assert complete_week_range(datetime.date(2025, 3, 1), datetime.date(2025, 5, 31)) == \
        ("2025-03-03", "2025-05-25")
