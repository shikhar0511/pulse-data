# Recidiviz - a data platform for criminal justice reform
# Copyright (C) 2022 Recidiviz, Inc.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
# =============================================================================
"""Tests capabilities of the BigQuery emulator."""
import datetime
from datetime import date

from google.cloud import bigquery

from recidiviz.big_query.big_query_address import BigQueryAddress
from recidiviz.tests.big_query.big_query_emulator_test_case import (
    BigQueryEmulatorTestCase,
)

_DATASET_1 = "dataset_1"
_TABLE_1 = "table_1"


class TestBigQueryEmulator(BigQueryEmulatorTestCase):
    """Tests capabilities of the BigQuery emulator."""

    def test_no_tables(self) -> None:
        """Run a simple query that does not query any tables."""
        query = """
SELECT *
FROM UNNEST([
   STRUCT(1 AS a, 2 AS b), STRUCT(3 AS a, 4 AS b)
]);
"""
        self.run_query_test(
            query,
            expected_result=[
                {"a": 1, "b": 2},
                {"a": 3, "b": 4},
            ],
        )

    def test_select_except(self) -> None:
        """Run a simple SELECT query with an EXCEPT clause."""
        query = """
SELECT * EXCEPT(b)
FROM UNNEST([
   STRUCT(1 AS a, 2 AS b), STRUCT(3 AS a, 4 AS b)
]);
"""
        self.run_query_test(
            query,
            expected_result=[
                {"a": 1},
                {"a": 3},
            ],
        )

    def test_select_qualify(self) -> None:
        """Run a simple query that has a QUALIFY clause."""

        query = """
SELECT *
FROM UNNEST([
   STRUCT(1 AS a, 2 AS b), STRUCT(3 AS a, 4 AS b)
])
WHERE TRUE
QUALIFY ROW_NUMBER() OVER (ORDER BY b DESC) = 1;
"""

        self.run_query_test(
            query,
            expected_result=[{"a": 3, "b": 4}],
        )

    def test_query_empty_table(self) -> None:
        address = BigQueryAddress(dataset_id=_DATASET_1, table_id=_TABLE_1)
        self.create_mock_table(
            address,
            schema=[
                bigquery.SchemaField(
                    "a",
                    field_type=bigquery.enums.SqlTypeNames.INTEGER.value,
                    mode="REQUIRED",
                ),
                bigquery.SchemaField(
                    "b",
                    field_type=bigquery.enums.SqlTypeNames.STRING.value,
                    mode="NULLABLE",
                ),
            ],
        )

        self.run_query_test(
            f"SELECT a, b FROM `{self.project_id}.{address.dataset_id}.{address.table_id}`;",
            expected_result=[],
        )

    def test_query_simple_table(self) -> None:
        address = BigQueryAddress(dataset_id=_DATASET_1, table_id=_TABLE_1)
        self.create_mock_table(
            address,
            schema=[
                bigquery.SchemaField(
                    "a",
                    field_type=bigquery.enums.SqlTypeNames.INTEGER.value,
                    mode="REQUIRED",
                ),
                bigquery.SchemaField(
                    "b",
                    field_type=bigquery.enums.SqlTypeNames.STRING.value,
                    mode="NULLABLE",
                ),
            ],
        )
        self.load_rows_into_table(
            address,
            data=[{"a": 1, "b": "foo"}, {"a": 3, "b": None}],
        )

        self.run_query_test(
            f"SELECT a, b FROM `{self.project_id}.{address.dataset_id}.{address.table_id}`;",
            expected_result=[{"a": 1, "b": "foo"}, {"a": 3, "b": None}],
        )

    def test_delete_and_recreate_table(self) -> None:
        """Test that confirms https://github.com/goccy/bigquery-emulator/issues/16 has
        been resolved."""
        address = BigQueryAddress(dataset_id=_DATASET_1, table_id=_TABLE_1)
        schema = [
            bigquery.SchemaField(
                "a",
                field_type=bigquery.enums.SqlTypeNames.INTEGER.value,
                mode="REQUIRED",
            ),
        ]
        self.create_mock_table(address, schema=schema)
        self.bq_client.delete_table(
            dataset_id=address.dataset_id, table_id=address.table_id
        )

        # Should not crash
        self.create_mock_table(address, schema=schema)

    def test_delete_and_recreate_table_different_schema(self) -> None:
        address = BigQueryAddress(dataset_id=_DATASET_1, table_id=_TABLE_1)
        schema_1 = [
            bigquery.SchemaField(
                "a",
                field_type=bigquery.enums.SqlTypeNames.INTEGER.value,
                mode="REQUIRED",
            ),
        ]
        self.create_mock_table(address, schema=schema_1)

        self.run_query_test(
            f"SELECT a FROM `{self.project_id}.{address.dataset_id}.{address.table_id}`",
            expected_result=[],
        )

        self.bq_client.delete_table(
            dataset_id=address.dataset_id, table_id=address.table_id
        )

        schema_2 = [
            bigquery.SchemaField(
                "b",
                field_type=bigquery.enums.SqlTypeNames.STRING.value,
                mode="REQUIRED",
            ),
        ]
        # Should not crash
        self.create_mock_table(address, schema=schema_2)

        # Should be a valid query now
        self.run_query_test(
            f"SELECT b FROM `{self.project_id}.{address.dataset_id}.{address.table_id}`",
            expected_result=[],
        )

    def test_create_two_tables_same_name_different_dataset(self) -> None:
        """Test that confirms https://github.com/goccy/bigquery-emulator/issues/18 has
        been resolved."""
        address_1 = BigQueryAddress(dataset_id=_DATASET_1, table_id=_TABLE_1)
        schema_1 = [
            bigquery.SchemaField(
                "a",
                field_type=bigquery.enums.SqlTypeNames.INTEGER.value,
                mode="REQUIRED",
            ),
        ]
        address_2 = BigQueryAddress(dataset_id="dataset_5", table_id=_TABLE_1)
        schema_2 = [
            bigquery.SchemaField(
                "b",
                field_type=bigquery.enums.SqlTypeNames.INTEGER.value,
                mode="REQUIRED",
            ),
        ]

        self.create_mock_table(address_1, schema_1)
        self.create_mock_table(address_2, schema_2)

        table_1 = self.bq_client.get_table(
            self.bq_client.dataset_ref_for_id(address_1.dataset_id), address_1.table_id
        )

        self.assertEqual(address_1.dataset_id, table_1.dataset_id)
        self.assertEqual(address_1.table_id, table_1.table_id)
        self.assertEqual(schema_1, table_1.schema)
        table_2 = self.bq_client.get_table(
            self.bq_client.dataset_ref_for_id(address_2.dataset_id), address_2.table_id
        )
        self.assertEqual(address_2.dataset_id, table_2.dataset_id)
        self.assertEqual(address_2.table_id, table_2.table_id)
        self.assertEqual(schema_2, table_2.schema)

        self.run_query_test(
            f"SELECT a FROM `{self.project_id}.{address_1.dataset_id}.{address_1.table_id}`",
            expected_result=[],
        )
        self.run_query_test(
            f"SELECT b FROM `{self.project_id}.{address_2.dataset_id}.{address_2.table_id}`",
            expected_result=[],
        )

        self.bq_client.stream_into_table(
            self.bq_client.dataset_ref_for_id(address_1.dataset_id),
            address_1.table_id,
            rows=[{"a": 1}],
        )
        self.bq_client.stream_into_table(
            self.bq_client.dataset_ref_for_id(address_2.dataset_id),
            address_2.table_id,
            rows=[{"b": 2}],
        )

        self.run_query_test(
            f"SELECT a FROM `{self.project_id}.{address_1.dataset_id}.{address_1.table_id}`",
            expected_result=[{"a": 1}],
        )
        self.run_query_test(
            f"SELECT b FROM `{self.project_id}.{address_2.dataset_id}.{address_2.table_id}`",
            expected_result=[{"b": 2}],
        )

    def test_query_min_max_integers(self) -> None:
        address = BigQueryAddress(dataset_id=_DATASET_1, table_id=_TABLE_1)
        self.create_mock_table(
            address,
            schema=[
                bigquery.SchemaField(
                    "a",
                    field_type=bigquery.enums.SqlTypeNames.INTEGER.value,
                    mode="REQUIRED",
                ),
                bigquery.SchemaField(
                    "b",
                    field_type=bigquery.enums.SqlTypeNames.INTEGER.value,
                    mode="NULLABLE",
                ),
            ],
        )
        self.load_rows_into_table(
            address,
            data=[{"a": 1, "b": 2}, {"a": 3, "b": 4}],
        )

        self.run_query_test(
            f"SELECT MIN(a) AS min_a, MAX(b) AS max_b "
            f"FROM `{self.project_id}.{address.dataset_id}.{address.table_id}`;",
            expected_result=[{"min_a": 1, "max_b": 4}],
        )

    def test_query_min_max_dates(self) -> None:
        address = BigQueryAddress(dataset_id=_DATASET_1, table_id=_TABLE_1)
        self.create_mock_table(
            address,
            schema=[
                bigquery.SchemaField(
                    "a",
                    field_type=bigquery.enums.SqlTypeNames.DATE.value,
                    mode="REQUIRED",
                ),
                bigquery.SchemaField(
                    "b",
                    field_type=bigquery.enums.SqlTypeNames.DATE.value,
                    mode="NULLABLE",
                ),
            ],
        )
        self.load_rows_into_table(
            address,
            data=[
                {"a": "2022-01-01", "b": "2022-02-02"},
                {"a": "2022-03-03", "b": "2022-04-04"},
            ],
        )

        self.run_query_test(
            f"SELECT MIN(a) AS min_a, MAX(b) AS max_b "
            f"FROM `{self.project_id}.{address.dataset_id}.{address.table_id}`;",
            expected_result=[{"min_a": date(2022, 1, 1), "max_b": date(2022, 4, 4)}],
        )

    def test_query_min_max_dates_with_partition(self) -> None:
        """Tests resolution of https://github.com/goccy/bigquery-emulator/issues/31."""
        address = BigQueryAddress(dataset_id=_DATASET_1, table_id=_TABLE_1)
        self.create_mock_table(
            address,
            schema=[
                bigquery.SchemaField(
                    "a",
                    field_type=bigquery.enums.SqlTypeNames.DATE.value,
                    mode="REQUIRED",
                ),
                bigquery.SchemaField(
                    "b",
                    field_type=bigquery.enums.SqlTypeNames.DATE.value,
                    mode="NULLABLE",
                ),
            ],
        )
        self.load_rows_into_table(
            address,
            data=[
                {"a": "2022-01-01", "b": "2022-03-03"},
                {"a": "2022-02-02", "b": "2022-03-03"},
                {"a": "2022-02-02", "b": "2022-04-04"},
            ],
        )

        self.run_query_test(
            f"SELECT MIN(a) OVER (PARTITION BY b) AS min_a, MAX(b) OVER (PARTITION BY a) AS max_b "
            f"FROM `{self.project_id}.{address.dataset_id}.{address.table_id}`;",
            expected_result=[
                {
                    "min_a": datetime.date(2022, 1, 1),
                    "max_b": datetime.date(2022, 3, 3),
                },
                {
                    "min_a": datetime.date(2022, 1, 1),
                    "max_b": datetime.date(2022, 4, 4),
                },
                {
                    "min_a": datetime.date(2022, 2, 2),
                    "max_b": datetime.date(2022, 4, 4),
                },
            ],
        )

    def test_query_min_with_parition(self) -> None:
        """Tests resolution of https://github.com/goccy/bigquery-emulator/issues/19."""
        self.run_query_test(
            """SELECT MIN(a) OVER (PARTITION BY b) AS min_a
FROM UNNEST([STRUCT(1 AS a, 2 AS b)]);""",
            expected_result=[{"min_a": 1}],
        )

    def test_query_max_with_parition(self) -> None:
        """Tests resolution of https://github.com/goccy/bigquery-emulator/issues/19."""
        self.run_query_test(
            """SELECT MAX(a) OVER (PARTITION BY b) AS max_a
FROM UNNEST([STRUCT(1 AS a, 2 AS b)]);""",
            expected_result=[{"max_a": 1}],
        )

    def test_query_count_with_parition(self) -> None:
        """Tests resolution of https://github.com/goccy/bigquery-emulator/issues/19."""
        self.run_query_test(
            """SELECT COUNT(a) OVER (PARTITION BY b) AS count_a
FROM UNNEST([STRUCT(1 AS a, 2 AS b)]);""",
            expected_result=[{"count_a": 1}],
        )

    def test_query_sum_with_parition(self) -> None:
        self.run_query_test(
            """SELECT SUM(a) OVER (PARTITION BY b) AS sum_a
FROM UNNEST([STRUCT(1 AS a, 2 AS b)]);""",
            expected_result=[{"sum_a": 1}],
        )

    def test_query_avg_with_parition(self) -> None:
        self.run_query_test(
            """SELECT AVG(a) OVER (PARTITION BY b) AS avg_a
FROM UNNEST([STRUCT(1 AS a, 2 AS b)]);""",
            expected_result=[{"avg_a": 1.0}],
        )

    def test_array_type(self) -> None:
        """Tests resolution of https://github.com/goccy/bigquery-emulator/issues/20."""
        query = "SELECT [1, 2, 3] as a;"
        self.run_query_test(
            query,
            expected_result=[{"a": [1, 2, 3]}],
        )

    def test_safe_parse_date_valid(self) -> None:
        self.run_query_test(
            """SELECT SAFE.PARSE_DATE("%m/%d/%Y", "12/25/2008") as a;""",
            expected_result=[{"a": date(2008, 12, 25)}],
        )

    def test_safe_parse_date_invalid(self) -> None:
        """Tests resolution of https://github.com/goccy/bigquery-emulator/issues/149."""
        self.run_query_test(
            """SELECT SAFE.PARSE_DATE("%m/%d/%Y", "2008-12-25") as a;""",
            expected_result=[{"a": None}],
        )

    def test_safe_parse_date_on_julian_date(self) -> None:
        """Tests resolution of goccy/go-zetasqlite#196"""
        self.run_query_test(
            """SELECT SAFE.PARSE_DATE('%y%j', '85001') AS a;""",
            expected_result=[{"a": date(1985, 1, 1)}],
        )

    def test_array_to_json(self) -> None:
        # Tests resolution to https://github.com/goccy/bigquery-emulator/issues/24.
        query = "SELECT TO_JSON([1, 2, 3]) as a;"
        self.run_query_test(
            query,
            expected_result=[{"a": [1, 2, 3]}],
        )

    def test_to_json(self) -> None:
        query = """SELECT TO_JSON(
  STRUCT("foo" AS a, 1 AS b)
) AS result;"""

        self.run_query_test(
            query,
            expected_result=[{"result": {"a": "foo", "b": 1}}],
        )

    def test_to_json_nested(self) -> None:
        query = """SELECT TO_JSON(
  STRUCT("foo" AS a, TO_JSON(STRUCT("bar" AS c)) AS b)
) AS result;"""

        self.run_query_test(
            query,
            expected_result=[{"result": {"a": "foo", "b": {"c": "bar"}}}],
        )

    def test_to_json_nested_cte(self) -> None:
        query = """WITH inner_json AS (
  SELECT TO_JSON(STRUCT("bar" AS c)) AS b
)
SELECT TO_JSON(STRUCT("foo" as a, b)) AS result
FROM inner_json;"""

        self.run_query_test(
            query,
            expected_result=[{"result": {"a": "foo", "b": {"c": "bar"}}}],
        )

    def test_to_json_nested_cte_column_rename(self) -> None:
        query = """WITH inner_json AS (
  SELECT TO_JSON(STRUCT("bar" AS c)) AS b
)
SELECT TO_JSON(STRUCT("foo" AS a, b AS b_2)) AS result
FROM inner_json;"""

        self.run_query_test(
            query,
            expected_result=[{"result": {"a": "foo", "b_2": {"c": "bar"}}}],
        )

    def test_to_json_nested_cte_numbers(self) -> None:
        query = """WITH inner_json AS (
    SELECT TO_JSON(STRUCT(1 AS c)) AS b
)
SELECT TO_JSON(STRUCT(2 as a, b)) AS result
FROM inner_json;"""

        self.run_query_test(
            query,
            expected_result=[{"result": {"a": 2, "b": {"c": 1}}}],
        )

    def test_to_json_nested_outer_array(self) -> None:
        query = """WITH inner_json AS (
    SELECT TO_JSON(STRUCT(1 AS c)) AS b
)
SELECT
TO_JSON([
    TO_JSON(STRUCT('foo' AS a, b))
]) AS result
FROM inner_json;"""

        self.run_query_test(
            query,
            expected_result=[{"result": [{"a": "foo", "b": {"c": 1}}]}],
        )

    def test_nested_json_array_agg(self) -> None:
        query = """WITH inner_table AS (
  SELECT * 
  FROM UNNEST([
    STRUCT(
      "foo" AS a, TO_JSON(STRUCT(1 AS b)) AS c
    )
  ])
)
SELECT TO_JSON(ARRAY_AGG(
    TO_JSON(STRUCT(a, c))
    ORDER BY a
)) AS result
FROM inner_table;"""
        self.run_query_test(
            query,
            expected_result=[{"result": [{"a": "foo", "c": {"b": 1}}]}],
        )

    def test_array_agg(self) -> None:
        query = """
SELECT b, ARRAY_AGG(a) AS a_list
FROM UNNEST([
   STRUCT(1 AS a, 2 AS b),
   STRUCT(3 AS a, 2 AS b)
])
GROUP BY b;
"""
        self.run_query_test(
            query,
            expected_result=[{"a_list": [1, 3], "b": 2}],
        )

    def test_array_agg_ignore_nulls_no_nulls(self) -> None:
        query = """
SELECT b, ARRAY_AGG(a IGNORE NULLS) AS a_list
FROM UNNEST([
   STRUCT(1 AS a, 2 AS b),
   STRUCT(3 AS a, 2 AS b)
])
GROUP BY b;
"""
        self.run_query_test(
            query,
            expected_result=[{"a_list": [1, 3], "b": 2}],
        )

    # TODO(https://github.com/goccy/bigquery-emulator/issues/34): File task for this
    def test_array_agg_ignore_nulls(self) -> None:
        address = BigQueryAddress(dataset_id=_DATASET_1, table_id=_TABLE_1)
        self.create_mock_table(
            address,
            schema=[
                bigquery.SchemaField(
                    "a",
                    field_type=bigquery.enums.SqlTypeNames.INTEGER.value,
                    mode="REQUIRED",
                ),
                bigquery.SchemaField(
                    "b",
                    field_type=bigquery.enums.SqlTypeNames.INTEGER.value,
                    mode="NULLABLE",
                ),
            ],
        )
        self.load_rows_into_table(
            address,
            data=[{"a": None, "b": 2}, {"a": 3, "b": 2}],
        )
        query = f"""
SELECT b, ARRAY_AGG(a IGNORE NULLS) AS a_list
FROM `{self.project_id}.{address.dataset_id}.{address.table_id}`
GROUP BY b;
"""
        self.run_query_test(
            query,
            expected_result=[{"a_list": [3], "b": 2}],
        )

    def test_array_agg_with_nulls(self) -> None:
        """Tests fix for https://github.com/goccy/bigquery-emulator/issues/33"""
        address = BigQueryAddress(dataset_id=_DATASET_1, table_id=_TABLE_1)
        self.create_mock_table(
            address,
            schema=[
                bigquery.SchemaField(
                    "a",
                    field_type=bigquery.enums.SqlTypeNames.INTEGER.value,
                    mode="REQUIRED",
                ),
                bigquery.SchemaField(
                    "b",
                    field_type=bigquery.enums.SqlTypeNames.INTEGER.value,
                    mode="NULLABLE",
                ),
            ],
        )
        self.load_rows_into_table(
            address,
            data=[{"a": None, "b": 2}, {"a": 3, "b": 2}],
        )
        query = f"""
SELECT b, ARRAY_AGG(a) AS a_list
FROM `{self.project_id}.{address.dataset_id}.{address.table_id}`
GROUP BY b;
"""
        with self.assertRaisesRegex(
            Exception, r"ARRAY_AGG: input value must be not null"
        ):
            self.run_query_test(
                query,
                expected_result=[{"a_list": [3], "b": 2}],
            )

    def test_null_in_unnest(self) -> None:
        """Tests resolution of https://github.com/goccy/bigquery-emulator/issues/30."""
        query = """
SELECT a
FROM UNNEST([
   STRUCT(NULL AS a)
]);
"""
        self.run_query_test(
            query,
            expected_result=[{"a": None}],
        )

    def test_date_in_unnest(self) -> None:
        """Tests resolution of https://github.com/goccy/bigquery-emulator/issues/30."""
        query = """
SELECT a
FROM UNNEST([
  STRUCT(DATE(2022, 1, 1) AS a)
]);
"""
        self.run_query_test(
            query,
            expected_result=[{"a": datetime.date(2022, 1, 1)}],
        )

    def test_cast_datetime_as_string(self) -> None:
        """Tests resolution of https://github.com/goccy/bigquery-emulator/issues/175."""
        self.run_query_test(
            """SELECT CAST(DATETIME(1987, 1, 25, 0, 0, 0) AS STRING)""",
            expected_result=[{"$col1": "1987-01-25 00:00:00"}],
        )

    def test_cast_datetime_as_string_with_format(self) -> None:
        """Tests resolution of https://github.com/goccy/bigquery-emulator/issues/175."""
        # TODO(goccy/bigquery-emulator#175): Change expected result to "SUNDAY, JANUARY 25 1987 AT 12:00:00" when fixed.
        self.run_query_test(
            """SELECT CAST(DATETIME(1987, 1, 25, 0, 0, 0) AS STRING FORMAT 'DAY"," MONTH DD YYYY "AT" HH":"MI":"SS')""",
            expected_result=[{"$col1": "1987-01-25 00:00:00"}],
        )
