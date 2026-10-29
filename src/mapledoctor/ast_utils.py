import re
from typing import Dict, List, Tuple, Optional, Any, Set
import sqlglot
from sqlglot import exp

DIALECT_MAP = {
    "SQLite": "sqlite",
    "DuckDB": "duckdb",
    "Postgres": "postgres",
    "PostgreSQL": "postgres",
    "Snowflake": "snowflake",
    "MySQL": "mysql",
}

def normalize_dialect(dialect: str) -> str:
    return DIALECT_MAP.get(dialect, "sqlite")

def parse_sql(sql: str, dialect: str = "SQLite") -> Optional[exp.Expression]:
    """Safely parses SQL into sqlglot AST expression, returns None on parse failure."""
    if not sql or not sql.strip():
        return None
    try:
        glot_dialect = normalize_dialect(dialect)
        return sqlglot.parse_one(sql.strip(), read=glot_dialect)
    except Exception:
        # Fallback to generic sqlglot parse
        try:
            return sqlglot.parse_one(sql.strip())
        except Exception:
            return None

def to_sql(expression: exp.Expression, dialect: str = "SQLite") -> str:
    """Serializes sqlglot AST expression back to dialect-formatted SQL."""
    glot_dialect = normalize_dialect(dialect)
    try:
        return expression.sql(dialect=glot_dialect)
    except Exception:
        return expression.sql()

def extract_tables_and_aliases(tree: exp.Expression) -> Dict[str, str]:
    """
    Extracts table references and their aliases from FROM and JOIN clauses.
    Returns: Dict mapping table_name.lower() -> alias (or table_name if no alias).
    Also returns reverse mapping alias.lower() -> table_name.
    """
    table_to_alias: Dict[str, str] = {}
    for table_node in tree.find_all(exp.Table):
        t_name = table_node.name
        if not t_name:
            continue
        alias = table_node.alias
        if alias:
            table_to_alias[t_name.lower()] = alias
        else:
            table_to_alias[t_name.lower()] = t_name
    return table_to_alias

def extract_aliases_to_table(tree: exp.Expression) -> Dict[str, str]:
    """Returns alias.lower() -> original_table_name."""
    alias_to_table: Dict[str, str] = {}
    for table_node in tree.find_all(exp.Table):
        t_name = table_node.name
        alias = table_node.alias
        if t_name and alias:
            alias_to_table[alias.lower()] = t_name
    return alias_to_table

def extract_columns(tree: exp.Expression) -> List[Tuple[Optional[str], str]]:
    """
    Extracts all column references as (table_or_alias, column_name).
    """
    cols = []
    for col_node in tree.find_all(exp.Column):
        tbl = col_node.table if col_node.table else None
        c_name = col_node.name
        if c_name:
            cols.append((tbl, c_name))
    return cols

def extract_functions(tree: exp.Expression) -> List[Tuple[str, List[exp.Expression]]]:
    """
    Extracts function calls: (function_name_upper, arguments_list).
    """
    funcs = []
    for func in tree.find_all(exp.Func, exp.Anonymous):
        fname = func.sql_name().upper() if hasattr(func, "sql_name") else func.key.upper()
        # Get expressions
        args = list(func.expressions) if hasattr(func, "expressions") and func.expressions else []
        if hasattr(func, "this") and func.this and func.this not in args:
            args.insert(0, func.this)
        funcs.append((fname, args))
    return funcs

def extract_division_nodes(tree: exp.Expression) -> List[exp.Div]:
    """Extracts division expressions."""
    return list(tree.find_all(exp.Div))

def is_integer_operand(expr: exp.Expression) -> bool:
    """Checks if expression represents an integer literal or COUNT() or integer cast."""
    if isinstance(expr, exp.Literal):
        val = expr.this
        return isinstance(val, int) or (isinstance(val, str) and val.isdigit())
    if isinstance(expr, (exp.Count, exp.Anonymous)):
        fname = expr.sql_name().upper() if hasattr(expr, "sql_name") else expr.key.upper()
        if fname == "COUNT":
            return True
    return False

def has_float_cast(expr: exp.Expression) -> bool:
    """Checks if expression is already wrapped in a float/real cast or 1.0 multiplication."""
    if isinstance(expr, exp.Cast):
        to_type = expr.to.sql().upper()
        if any(f in to_type for f in ["REAL", "FLOAT", "DOUBLE", "NUMERIC", "DECIMAL"]):
            return True
    if isinstance(expr, exp.Mul):
        # 1.0 * x
        if any(isinstance(a, exp.Literal) and "." in str(a.this) for a in [expr.this, expr.expression]):
            return True
    return False

def extract_join_equalities(tree: exp.Expression) -> List[Tuple[exp.Join, exp.EQ, Tuple[str, str], Tuple[str, str]]]:
    """
    Extracts JOIN nodes with equality ON condition.
    Returns: [(join_node, eq_node, (left_table, left_col), (right_table, right_col))]
    """
    results = []
    for join in tree.find_all(exp.Join):
        on_clause = join.args.get("on")
        if not on_clause:
            continue
        # Find all EQ nodes inside ON
        eq_nodes = [on_clause] if isinstance(on_clause, exp.EQ) else list(on_clause.find_all(exp.EQ))
        for eq in eq_nodes:
            left = eq.this
            right = eq.expression
            if isinstance(left, exp.Column) and isinstance(right, exp.Column):
                l_tbl = left.table or ""
                l_col = left.name
                r_tbl = right.table or ""
                r_col = right.name
                results.append((join, eq, (l_tbl, l_col), (r_tbl, r_col)))
    return results

def extract_subquery_equalities(tree: exp.Expression) -> List[Tuple[exp.EQ, exp.Column, exp.Expression]]:
    """
    Extracts equality comparisons where right side is a subquery.
    col = (SELECT ...)
    """
    results = []
    for eq in tree.find_all(exp.EQ):
        left = eq.this
        right = eq.expression
        if isinstance(left, exp.Column) and isinstance(right, (exp.Subquery, exp.Select)):
            results.append((eq, left, right))
        elif isinstance(right, exp.Column) and isinstance(left, (exp.Subquery, exp.Select)):
            results.append((eq, right, left))
    return results

def extract_order_by_columns(tree: exp.Expression) -> List[Tuple[str, Optional[str], bool]]:
    """
    Extracts (col_name, table_name, is_asc).
    """
    results = []
    for order in tree.find_all(exp.Order):
        for ordered in order.expressions:
            is_desc = bool(ordered.args.get("desc"))
            is_asc = not is_desc
            target = ordered.this
            if isinstance(target, exp.Column):
                results.append((target.name, target.table, is_asc))
    return results

def extract_min_max_columns(tree: exp.Expression) -> List[Tuple[str, str, Optional[str]]]:
    """
    Extracts ('MIN'|'MAX', col_name, table_name).
    """
    results = []
    for func in tree.find_all(exp.Min, exp.Max):
        op = "MIN" if isinstance(func, exp.Min) else "MAX"
        arg = func.this
        if isinstance(arg, exp.Column):
            results.append((op, arg.name, arg.table))
    return results

def has_null_filter(tree: exp.Expression, col_name: str, table_name: Optional[str] = None) -> bool:
    """Checks if WHERE clause already filters col IS NOT NULL."""
    # First quick check in SQL string
    sql_str = tree.sql()
    if re.search(rf'\b{re.escape(col_name)}\s+IS\s+NOT\s+NULL\b', sql_str, re.IGNORECASE):
        return True
    if re.search(rf'NOT\s+\b{re.escape(col_name)}\s+IS\s+NULL\b', sql_str, re.IGNORECASE):
        return True

    for is_null in tree.find_all(exp.Is):
        this_col = is_null.this
        if isinstance(this_col, exp.Column) and this_col.name.lower() == col_name.lower():
            if table_name and this_col.table and this_col.table.lower() != table_name.lower():
                continue
            right = is_null.expression
            if isinstance(right, exp.Not) and isinstance(right.this, exp.Null):
                return True
    return False

def add_is_not_null_to_where(sql: str, col_name: str, table_name: Optional[str] = None) -> str:
    """
    Adds col IS NOT NULL (or table.col IS NOT NULL) to the WHERE clause of SQL.
    Preserves all existing WHERE clauses.
    """
    tree = parse_sql(sql)
    if not tree:
        col_expr = f"{table_name}.{col_name}" if table_name else col_name
        if re.search(r'\bWHERE\b', sql, re.IGNORECASE):
            return re.sub(r'(\bWHERE\b\s+)', rf'\1{col_expr} IS NOT NULL AND ', sql, count=1, flags=re.IGNORECASE)
        elif re.search(r'\bORDER\s+BY\b', sql, re.IGNORECASE):
            return re.sub(r'(\bORDER\s+BY\b)', rf'WHERE {col_expr} IS NOT NULL \1', sql, count=1, flags=re.IGNORECASE)
        else:
            return f"{sql} WHERE {col_expr} IS NOT NULL"

    col_target = exp.Column(
        this=exp.to_identifier(col_name),
        table=exp.to_identifier(table_name) if table_name else None
    )
    is_not_null_expr = exp.Is(this=col_target, expression=exp.Not(this=exp.Null()))

    where_node = tree.find(exp.Where)
    if where_node:
        existing_cond = where_node.this
        new_cond = exp.And(this=existing_cond, expression=is_not_null_expr)
        where_node.set("this", new_cond)
    else:
        tree.set("where", exp.Where(this=is_not_null_expr))

    return to_sql(tree)
