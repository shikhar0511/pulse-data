# Recidiviz - a data platform for criminal justice reform
# Copyright (C) 2019 Recidiviz, Inc.
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
"""Tests for utils/execution_utils.py."""
# pylint: disable=protected-access
import unittest
from typing import Any, Dict, Iterable

from recidiviz.persistence.entity.state.entities import StateAssessment, StatePerson
from recidiviz.pipelines.utils.execution_utils import (
    extract_county_of_residence_from_rows,
    person_and_kwargs_for_identifier,
    select_all_by_person_query,
    select_query,
)


class TestPersonAndKwargsForIdentifier(unittest.TestCase):
    """Tests the person_and_kwargs_for_identifier function."""

    def test_person_and_kwargs_for_identifier(self) -> None:
        person_input = StatePerson.new_with_defaults(state_code="US_XX", person_id=123)

        assessment = StateAssessment.new_with_defaults(
            state_code="US_XX", external_id="a1"
        )

        arg_to_entities_map: Dict[str, Iterable[Any]] = {
            StatePerson.__name__: iter([person_input]),
            StateAssessment.__name__: iter([assessment]),
        }

        person, kwargs = person_and_kwargs_for_identifier(arg_to_entities_map)

        expected_kwargs = {StateAssessment.__name__: [assessment]}

        self.assertEqual(person, person_input)
        self.assertEqual(expected_kwargs, kwargs)

    def test_person_and_kwargs_for_identifier_two_people_same_id(self) -> None:
        person_input_1 = StatePerson.new_with_defaults(
            state_code="US_XX", person_id=123
        )

        person_input_2 = StatePerson.new_with_defaults(
            state_code="US_XX", person_id=123
        )

        assessment = StateAssessment.new_with_defaults(
            state_code="US_XX", external_id="a1"
        )

        arg_to_entities_map: Dict[str, Iterable[Any]] = {
            # There should never be two StatePerson entities with the same person_id. This should fail loudly.
            StatePerson.__name__: iter([person_input_1, person_input_2]),
            StateAssessment.__name__: iter([assessment]),
        }

        with self.assertRaises(ValueError):
            _ = person_and_kwargs_for_identifier(arg_to_entities_map)

    def test_person_and_kwargs_for_identifier_no_person(self) -> None:
        assessment = StateAssessment.new_with_defaults(
            state_code="US_XX", external_id="a1"
        )

        arg_to_entities_map: Dict[str, Iterable[Any]] = {
            # There should never be two StatePerson entities with the same person_id. This should fail loudly.
            StateAssessment.__name__: iter([assessment])
        }

        with self.assertRaises(KeyError):
            _ = person_and_kwargs_for_identifier(arg_to_entities_map)


class TestSelectAllQuery(unittest.TestCase):
    """Tests for the select_all_by_person_query AND select_query functions."""

    def setUp(self) -> None:
        self.project_id = "project-id"
        self.dataset = "my_dataset"
        self.table_id = "TABLE_WHERE_DATA_IS"

    def test_select_all_with_state_code_filter_only(self) -> None:
        expected_query = "SELECT * FROM `project-id.my_dataset.TABLE_WHERE_DATA_IS` WHERE state_code IN ('US_XX')"

        self.assertEqual(
            expected_query,
            select_all_by_person_query(
                self.project_id,
                self.dataset,
                self.table_id,
                state_code_filter="US_XX",
                person_id_filter_set=None,
            ),
        )

        self.assertEqual(
            expected_query,
            select_query(
                self.project_id,
                self.dataset,
                self.table_id,
                state_code_filter="US_XX",
                root_entity_id_field="field_name",
                root_entity_id_filter_set=None,
            ),
        )

    def test_select_all_state_code_and_ids_filter(self) -> None:
        expected_query = (
            "SELECT * FROM `project-id.my_dataset.TABLE_WHERE_DATA_IS` "
            "WHERE state_code IN ('US_XX') AND person_id IN (1234)"
        )

        self.assertEqual(
            expected_query,
            select_all_by_person_query(
                self.project_id,
                self.dataset,
                self.table_id,
                state_code_filter="US_XX",
                person_id_filter_set={1234},
            ),
        )

        expected_query = (
            "SELECT * FROM `project-id.my_dataset.TABLE_WHERE_DATA_IS` "
            "WHERE state_code IN ('US_XX') AND field_name IN (1234, 56)"
        )
        self.assertEqual(
            expected_query,
            select_query(
                self.project_id,
                self.dataset,
                self.table_id,
                state_code_filter="US_XX",
                root_entity_id_field="field_name",
                root_entity_id_filter_set={1234, 56},
            ),
        )


class TestExtractCountyOfResidenceFromRows(unittest.TestCase):
    """Tests for extract_county_of_residence_from_rows in execution_utils.py."""

    def test_no_rows(self) -> None:
        county_of_residence = extract_county_of_residence_from_rows([])
        self.assertIsNone(county_of_residence)

    def test_single_row(self) -> None:
        expected_county_of_residence = "county"
        rows = [
            {
                "state_code": "US_XX",
                "person_id": 123,
                "county_of_residence": expected_county_of_residence,
            }
        ]

        county_of_residence = extract_county_of_residence_from_rows(rows)
        self.assertEqual(expected_county_of_residence, county_of_residence)

    def test_multiple_rows_asserts(self) -> None:
        rows = [
            {
                "state_code": "US_XX",
                "person_id": 123,
                "county_of_residence": "county_1",
            },
            {
                "state_code": "US_XX",
                "person_id": 123,
                "county_of_residence": "county_2",
            },
        ]

        with self.assertRaisesRegex(
            ValueError,
            r"^Found more than one county of residence for person with id \[123\]",
        ):
            _ = extract_county_of_residence_from_rows(rows)
