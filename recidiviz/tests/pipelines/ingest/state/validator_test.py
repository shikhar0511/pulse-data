# Recidiviz - a data platform for criminal justice reform
# Copyright (C) 2023 Recidiviz, Inc.
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
"""Unit tests to test validations for ingested entities."""
import unittest
from datetime import date, datetime
from typing import Dict, List, Type

import sqlalchemy
from more_itertools import one

from recidiviz.common.constants.state.state_charge import StateChargeV2Status
from recidiviz.common.constants.state.state_sentence import (
    StateSentenceStatus,
    StateSentenceType,
)
from recidiviz.common.constants.state.state_task_deadline import StateTaskType
from recidiviz.persistence.database.schema.state import schema
from recidiviz.persistence.database.schema_utils import (
    get_database_entity_by_table_name,
)
from recidiviz.persistence.entity.base_entity import Entity
from recidiviz.persistence.entity.entity_utils import (
    CoreEntityFieldIndex,
    get_all_entity_classes_in_module,
)
from recidiviz.persistence.entity.state import entities as entities_schema
from recidiviz.persistence.entity.state import entities as state_entities
from recidiviz.persistence.entity.state.entities import (
    StatePersonExternalId,
    StateStaffExternalId,
    StateTaskDeadline,
)
from recidiviz.pipelines.ingest.state.validator import validate_root_entity


class TestEntityValidations(unittest.TestCase):
    """Tests validations functions"""

    def setUp(self) -> None:
        self.field_index = CoreEntityFieldIndex()

    def test_valid_external_id_state_staff_entities(self) -> None:
        entity = state_entities.StateStaff(
            state_code="US_XX",
            staff_id=1111,
            external_ids=[
                StateStaffExternalId(
                    external_id="100",
                    state_code="US_XX",
                    id_type="US_XX_EMPLOYEE",
                ),
                StateStaffExternalId(
                    external_id="200",
                    state_code="US_XX",
                    id_type="US_EMP",
                ),
            ],
        )

        error_messages = validate_root_entity(entity, self.field_index)
        self.assertTrue(len(list(error_messages)) == 0)

    def test_missing_external_id_state_staff_entities(self) -> None:
        entity = state_entities.StateStaff(
            state_code="US_XX", staff_id=1111, external_ids=[]
        )

        error_messages = validate_root_entity(entity, self.field_index)
        self.assertRegex(
            one(error_messages),
            r"^Found \[StateStaff\] with id \[1111\] missing an external_id:",
        )

    def test_two_external_ids_same_type_state_staff_entities(self) -> None:
        entity = state_entities.StateStaff(
            state_code="US_XX",
            staff_id=1111,
            external_ids=[
                StateStaffExternalId(
                    external_id="100",
                    state_code="US_XX",
                    id_type="US_XX_EMPLOYEE",
                ),
                StateStaffExternalId(
                    external_id="200",
                    state_code="US_XX",
                    id_type="US_XX_EMPLOYEE",
                ),
            ],
        )

        error_messages = validate_root_entity(entity, self.field_index)
        self.assertRegex(
            one(error_messages),
            r"Duplicate external id types for \[StateStaff\] with id "
            r"\[1111\]: US_XX_EMPLOYEE",
        )

    def test_two_external_ids_exact_same_state_staff_entities(self) -> None:
        entity = state_entities.StateStaff(
            state_code="US_XX",
            staff_id=1111,
            external_ids=[
                StateStaffExternalId(
                    external_id="100",
                    state_code="US_XX",
                    id_type="US_XX_EMPLOYEE",
                ),
                StateStaffExternalId(
                    external_id="100",
                    state_code="US_XX",
                    id_type="US_XX_EMPLOYEE",
                ),
            ],
        )

        error_messages = validate_root_entity(entity, self.field_index)
        self.assertRegex(
            one(error_messages),
            r"Duplicate external id types for \[StateStaff\] with id "
            r"\[1111\]: US_XX_EMPLOYEE",
        )

    def test_valid_external_id_state_person_entities(self) -> None:
        entity = state_entities.StatePerson(
            state_code="US_XX",
            person_id=1111,
            external_ids=[
                StatePersonExternalId(
                    external_id="100",
                    state_code="US_XX",
                    id_type="US_XX_EMPLOYEE",
                ),
            ],
        )

        error_messages = validate_root_entity(entity, self.field_index)
        self.assertTrue(len(list(error_messages)) == 0)

    def test_missing_external_id_state_person_entities(self) -> None:
        entity = state_entities.StatePerson(
            state_code="US_XX", person_id=1111, external_ids=[]
        )

        error_messages = validate_root_entity(entity, self.field_index)
        self.assertRegex(
            one(error_messages),
            r"^Found \[StatePerson\] with id \[1111\] missing an external_id:",
        )

    def test_two_external_ids_same_type_state_person_entities(self) -> None:
        entity = state_entities.StatePerson(
            state_code="US_XX",
            person_id=1111,
            external_ids=[
                StatePersonExternalId(
                    external_id="100",
                    state_code="US_XX",
                    id_type="US_XX_EMPLOYEE",
                ),
                StatePersonExternalId(
                    external_id="200",
                    state_code="US_XX",
                    id_type="US_XX_EMPLOYEE",
                ),
            ],
        )

        error_messages = validate_root_entity(entity, self.field_index)
        self.assertRegex(
            one(error_messages),
            r"Duplicate external id types for \[StatePerson\] with id "
            r"\[1111\]: US_XX_EMPLOYEE",
        )

    def test_two_external_ids_exact_same_state_person_entities(self) -> None:
        entity = state_entities.StatePerson(
            state_code="US_XX",
            person_id=1111,
            external_ids=[
                StatePersonExternalId(
                    external_id="100",
                    state_code="US_XX",
                    id_type="US_XX_EMPLOYEE",
                ),
                StatePersonExternalId(
                    external_id="100",
                    state_code="US_XX",
                    id_type="US_XX_EMPLOYEE",
                ),
            ],
        )

        error_messages = validate_root_entity(entity, self.field_index)
        self.assertRegex(
            one(error_messages),
            r"Duplicate external id types for \[StatePerson\] with id "
            r"\[1111\]: US_XX_EMPLOYEE",
        )

    def test_entity_tree_unique_constraints_simple_valid(self) -> None:
        person = state_entities.StatePerson(
            state_code="US_XX",
            person_id=3111,
            external_ids=[
                StatePersonExternalId(
                    person_external_id_id=11114,
                    state_code="US_XX",
                    external_id="4001",
                    id_type="PERSON",
                ),
            ],
        )

        person.task_deadlines.append(
            StateTaskDeadline(
                task_deadline_id=1,
                state_code="US_XX",
                task_type=StateTaskType.DISCHARGE_FROM_INCARCERATION,
                eligible_date=date(2020, 9, 11),
                update_datetime=datetime(2023, 2, 1, 11, 19),
                task_metadata='{"external_id": "00000001-111123-371006", "sentence_type": "INCARCERATION"}',
                person=person,
            )
        )

        person.task_deadlines.append(
            StateTaskDeadline(
                task_deadline_id=3,
                state_code="US_XX",
                task_type=StateTaskType.INTERNAL_UNKNOWN,
                eligible_date=date(2020, 9, 11),
                update_datetime=datetime(2023, 2, 1, 11, 19),
                task_metadata='{"external_id": "00000001-111123-371006", "sentence_type": "INCARCERATION"}',
                person=person,
            )
        )

        error_messages = validate_root_entity(person, self.field_index)
        self.assertTrue(len(list(error_messages)) == 0)

    def test_entity_tree_unique_constraints_simple_invalid(self) -> None:
        person = state_entities.StatePerson(
            state_code="US_XX",
            person_id=3111,
            external_ids=[
                StatePersonExternalId(
                    person_external_id_id=11114,
                    state_code="US_XX",
                    external_id="4001",
                    id_type="PERSON",
                ),
            ],
        )

        person.task_deadlines.append(
            StateTaskDeadline(
                task_deadline_id=1,
                state_code="US_XX",
                task_type=StateTaskType.DISCHARGE_FROM_INCARCERATION,
                task_subtype=None,
                eligible_date=date(2020, 9, 11),
                update_datetime=datetime(2023, 2, 1, 11, 19),
                task_metadata='{"external_id": "00000001-111123-371006", "sentence_type": "INCARCERATION"}',
                person=person,
            )
        )

        # Add exact duplicate (only primary key is changed)
        person.task_deadlines.append(
            StateTaskDeadline(
                task_deadline_id=2,
                state_code="US_XX",
                task_type=StateTaskType.DISCHARGE_FROM_INCARCERATION,
                task_subtype=None,
                eligible_date=date(2020, 9, 11),
                update_datetime=datetime(2023, 2, 1, 11, 19),
                task_metadata='{"external_id": "00000001-111123-371006", "sentence_type": "INCARCERATION"}',
                person=person,
            )
        )
        # Add similar with different task_type
        person.task_deadlines.append(
            StateTaskDeadline(
                task_deadline_id=3,
                state_code="US_XX",
                task_type=StateTaskType.INTERNAL_UNKNOWN,
                task_subtype=None,
                eligible_date=date(2020, 9, 11),
                update_datetime=datetime(2023, 2, 1, 11, 19),
                task_metadata='{"external_id": "00000001-111123-371006", "sentence_type": "INCARCERATION"}',
                person=person,
            )
        )

        error_messages = validate_root_entity(person, self.field_index)
        self.assertEqual(
            error_messages[0],
            (
                "Found [2] state_task_deadline entities with (state_code=US_XX, "
                "task_type=StateTaskType.DISCHARGE_FROM_INCARCERATION, "
                "task_subtype=None, "
                'task_metadata={"external_id": "00000001-111123-371006", "sentence_type": "INCARCERATION"}, '
                "update_datetime=2023-02-01 11:19:00). First 2 entities found:\n"
                "  * StateTaskDeadline(task_deadline_id=1)\n"
                "  * StateTaskDeadline(task_deadline_id=2)"
            ),
        )
        self.assertIn(
            "If sequence_num is None, then the ledger's partition_key must be unique across hydrated entities.",
            error_messages[1],
        )

    def test_entity_tree_unique_constraints_invalid_all_nonnull(self) -> None:
        person = state_entities.StatePerson(
            state_code="US_XX",
            person_id=3111,
            external_ids=[
                StatePersonExternalId(
                    person_external_id_id=11114,
                    state_code="US_XX",
                    external_id="4001",
                    id_type="PERSON",
                ),
            ],
        )

        person.task_deadlines.append(
            StateTaskDeadline(
                task_deadline_id=1,
                state_code="US_XX",
                task_type=StateTaskType.DISCHARGE_FROM_INCARCERATION,
                task_subtype="my_subtype",
                eligible_date=date(2020, 9, 11),
                update_datetime=datetime(2023, 2, 1, 11, 19),
                task_metadata='{"external_id": "00000001-111123-371006", "sentence_type": "INCARCERATION"}',
                person=person,
            )
        )

        # Add exact duplicate (only primary key is changed)
        person.task_deadlines.append(
            StateTaskDeadline(
                task_deadline_id=2,
                state_code="US_XX",
                task_type=StateTaskType.DISCHARGE_FROM_INCARCERATION,
                task_subtype="my_subtype",
                eligible_date=date(2020, 9, 11),
                update_datetime=datetime(2023, 2, 1, 11, 19),
                task_metadata='{"external_id": "00000001-111123-371006", "sentence_type": "INCARCERATION"}',
                person=person,
            )
        )

        error_messages = validate_root_entity(person, self.field_index)
        expected_duplicate_error = (
            "Found [2] state_task_deadline entities with (state_code=US_XX, "
            "task_type=StateTaskType.DISCHARGE_FROM_INCARCERATION, "
            "task_subtype=my_subtype, "
            'task_metadata={"external_id": "00000001-111123-371006", "sentence_type": "INCARCERATION"}, '
            "update_datetime=2023-02-01 11:19:00). First 2 entities found:\n"
            "  * StateTaskDeadline(task_deadline_id=1)\n"
            "  * StateTaskDeadline(task_deadline_id=2)"
        )
        expected_sequence_num_error = "If sequence_num is None, then the ledger's partition_key must be unique across hydrated entities."
        self.assertEqual(expected_duplicate_error, error_messages[0])
        self.assertIn(expected_sequence_num_error, error_messages[1])

    def test_entity_tree_unique_constraints_task_deadline_valid_tree(self) -> None:
        person = state_entities.StatePerson(
            state_code="US_XX",
            person_id=3111,
            external_ids=[
                StatePersonExternalId(
                    person_external_id_id=11114,
                    state_code="US_XX",
                    external_id="4001",
                    id_type="PERSON",
                ),
            ],
        )

        person.task_deadlines.append(
            StateTaskDeadline(
                task_deadline_id=1,
                state_code="US_XX",
                task_type=StateTaskType.DISCHARGE_FROM_INCARCERATION,
                eligible_date=date(2020, 9, 11),
                update_datetime=datetime(2023, 2, 1, 11, 19),
                task_metadata='{"external_id": "00000001-111123-371006", "sentence_type": "INCARCERATION"}',
                person=person,
            )
        )

        person.task_deadlines.append(
            # Task is exactly identical except for task_deadline_id and task_metadata
            StateTaskDeadline(
                task_deadline_id=2,
                state_code="US_XX",
                task_type=StateTaskType.DISCHARGE_FROM_INCARCERATION,
                eligible_date=date(2020, 9, 11),
                update_datetime=datetime(2023, 2, 1, 11, 19),
                task_metadata='{"external_id": "00000001-111123-371006", "sentence_type": "SUPERVISION"}',
                person=person,
            )
        )

        error_messages = validate_root_entity(person, self.field_index)
        self.assertTrue(len(list(error_messages)) == 0)

    def test_multiple_errors_returned_for_root_enities(self) -> None:
        person = state_entities.StatePerson(
            state_code="US_XX",
            person_id=3111,
            external_ids=[],
        )

        person.task_deadlines.append(
            StateTaskDeadline(
                task_deadline_id=1,
                state_code="US_XX",
                task_type=StateTaskType.DISCHARGE_FROM_INCARCERATION,
                eligible_date=date(2020, 9, 11),
                update_datetime=datetime(2023, 2, 1, 11, 19),
                task_metadata='{"external_id": "00000001-111123-371006", "sentence_type": "INCARCERATION"}',
                person=person,
            )
        )

        # Add exact duplicate (only primary key is changed)
        person.task_deadlines.append(
            StateTaskDeadline(
                task_deadline_id=2,
                state_code="US_XX",
                task_type=StateTaskType.DISCHARGE_FROM_INCARCERATION,
                eligible_date=date(2020, 9, 11),
                update_datetime=datetime(2023, 2, 1, 11, 19),
                task_metadata='{"external_id": "00000001-111123-371006", "sentence_type": "INCARCERATION"}',
                person=person,
            )
        )
        # Add similar with different task_type
        person.task_deadlines.append(
            StateTaskDeadline(
                task_deadline_id=3,
                state_code="US_XX",
                task_type=StateTaskType.INTERNAL_UNKNOWN,
                eligible_date=date(2020, 9, 11),
                update_datetime=datetime(2023, 2, 1, 11, 19),
                task_metadata='{"external_id": "00000001-111123-371006", "sentence_type": "INCARCERATION"}',
                person=person,
            )
        )

        error_messages = validate_root_entity(person, self.field_index)
        self.assertEqual(3, len(error_messages))
        self.assertRegex(
            error_messages[0],
            r"^Found \[StatePerson\] with id \[3111\] missing an external_id:",
        )
        expected_duplicate_error = (
            "Found [2] state_task_deadline entities with (state_code=US_XX, "
            "task_type=StateTaskType.DISCHARGE_FROM_INCARCERATION, "
            "task_subtype=None, "
            'task_metadata={"external_id": "00000001-111123-371006", "sentence_type": "INCARCERATION"}, '
            "update_datetime=2023-02-01 11:19:00). First 2 entities found:\n"
            "  * StateTaskDeadline(task_deadline_id=1)\n"
            "  * StateTaskDeadline(task_deadline_id=2)"
        )
        self.assertEqual(expected_duplicate_error, error_messages[1])
        expected_ledger_error = "If sequence_num is None, then the ledger's partition_key must be unique across hydrated entities."
        self.assertIn(expected_ledger_error, error_messages[2])


class TestUniqueConstraintValid(unittest.TestCase):
    """Test that unique constraints specified on entities are valid"""

    def test_valid_field_columns_in_entities(self) -> None:
        all_entities = get_all_entity_classes_in_module(entities_schema)
        for entity in all_entities:
            constraints = entity.global_unique_constraints()
            entity_attrs = [a.name for a in entity.__dict__["__attrs_attrs__"]]
            for constraint in constraints:
                for column_name in constraint.fields:
                    self.assertTrue(column_name in entity_attrs)

    def test_valid_field_columns_in_schema(self) -> None:
        all_entities = get_all_entity_classes_in_module(entities_schema)
        for entity in all_entities:
            constraints = entity.global_unique_constraints()
            schema_entity = get_database_entity_by_table_name(
                schema, entity.get_entity_name()
            )
            for constraint in constraints:
                for column_name in constraint.fields:
                    self.assertTrue(hasattr(schema_entity, column_name))

    def test_equal_schema_uniqueness_constraint(self) -> None:
        expected_missing_schema_constraints: Dict[Type[Entity], List[str]] = {
            state_entities.StateTaskDeadline: [
                "state_task_deadline_unique_per_person_update_date_type"
            ]
        }
        all_entities = get_all_entity_classes_in_module(entities_schema)
        for entity in all_entities:
            constraints = (
                entity.global_unique_constraints()
                + entity.entity_tree_unique_constraints()
            )
            schema_entity = get_database_entity_by_table_name(
                schema, entity.get_entity_name()
            )
            constraint_names = [constraint.name for constraint in constraints]

            expected_missing = expected_missing_schema_constraints.get(entity) or []
            schema_constraint_names = [
                arg.name
                for arg in schema_entity.__table_args__
                if isinstance(arg, sqlalchemy.UniqueConstraint)
            ] + expected_missing
            self.assertListEqual(constraint_names, schema_constraint_names)


class TestSentencingRootEntityChecks(unittest.TestCase):
    """Test that root entity checks specific to the sentencing schema are valid."""

    def setUp(self) -> None:
        self.field_index = CoreEntityFieldIndex()
        self.state_code = "US_XX"
        self.state_person = state_entities.StatePerson(
            state_code=self.state_code,
            person_id=1,
            external_ids=[
                StatePersonExternalId(
                    external_id="1",
                    state_code="US_XX",
                    id_type="US_XX_TEST_PERSON",
                ),
            ],
        )

    def test_no_parole_possible_means_no_parole_projected_dates(
        self,
    ) -> None:
        """
        If a sentence has parole_possible=False, then there should be no parole related
        projected dates on all sentence_length entities.
        """
        sentence = state_entities.StateSentence(
            state_code=self.state_code,
            external_id="SENT-EXTERNAL-1",
            person=self.state_person,
            sentence_type=StateSentenceType.STATE_PRISON,
            imposed_date=date(2022, 1, 1),
            parole_possible=None,
            charges=[
                state_entities.StateChargeV2(
                    external_id="CHARGE",
                    state_code=self.state_code,
                    status=StateChargeV2Status.PRESENT_WITHOUT_INFO,
                )
            ],
            sentence_lengths=[
                state_entities.StateSentenceLength(
                    state_code=self.state_code,
                    length_update_datetime=datetime(2022, 1, 1),
                    parole_eligibility_date_external=date(2025, 1, 1),
                ),
            ],
        )
        self.state_person.sentences = [sentence]
        errors = validate_root_entity(self.state_person, self.field_index)
        self.assertEqual(errors, [])

        sentence.parole_possible = True
        self.state_person.sentences = [sentence]
        errors = validate_root_entity(self.state_person, self.field_index)
        self.assertEqual(errors, [])

        sentence.parole_possible = False
        self.state_person.sentences = [sentence]
        errors = validate_root_entity(self.state_person, self.field_index)
        self.assertEqual(
            errors[0],
            (
                "Sentence StateSentence(external_id='SENT-EXTERNAL-1', sentence_id=None) "
                "has parole projected dates, despite denoting that parole is not possible."
            ),
        )

    def test_sentences_have_charge_invalid(self) -> None:
        """Tests that sentences post root entity merge all have a sentence_type and imposed_date."""
        sentence = state_entities.StateSentence(
            state_code=self.state_code,
            external_id="SENT-EXTERNAL-1",
            person=self.state_person,
            sentence_type=StateSentenceType.STATE_PRISON,
            imposed_date=date(2022, 1, 1),
        )
        self.state_person.sentences.append(sentence)
        errors = validate_root_entity(self.state_person, self.field_index)
        self.assertEqual(len(errors), 1)
        self.assertEqual(
            "Found sentence StateSentence(external_id='SENT-EXTERNAL-1', sentence_id=None) with no charges.",
            errors[0],
        )

    def test_sentences_have_type_and_imposed_date_invalid(self) -> None:
        """Tests that sentences post root entity merge all have a sentence_type and imposed_date."""
        sentence = state_entities.StateSentence(
            state_code=self.state_code,
            external_id="SENT-EXTERNAL-1",
            person=self.state_person,
            charges=[
                state_entities.StateChargeV2(
                    external_id="CHARGE",
                    state_code=self.state_code,
                    status=StateChargeV2Status.PRESENT_WITHOUT_INFO,
                )
            ],
        )
        self.state_person.sentences.append(sentence)
        errors = validate_root_entity(self.state_person, self.field_index)
        self.assertEqual(len(errors), 2)
        self.assertEqual(
            "Found sentence StateSentence(external_id='SENT-EXTERNAL-1', sentence_id=None) with no imposed_date.",
            errors[0],
        )
        self.assertEqual(
            errors[1],
            "Found sentence StateSentence(external_id='SENT-EXTERNAL-1', sentence_id=None) with no StateSentenceType.",
        )

    def test_revoked_sentence_status_check_valid(self) -> None:
        probation_sentence = state_entities.StateSentence(
            state_code=self.state_code,
            external_id="SENT-EXTERNAL-1",
            sentence_type=StateSentenceType.PROBATION,
            imposed_date=date(2022, 1, 1),
            charges=[
                state_entities.StateChargeV2(
                    external_id="CHARGE",
                    state_code=self.state_code,
                    status=StateChargeV2Status.PRESENT_WITHOUT_INFO,
                )
            ],
            sentence_status_snapshots=[
                state_entities.StateSentenceStatusSnapshot(
                    state_code=self.state_code,
                    status=StateSentenceStatus.SERVING,
                    status_update_datetime=datetime(2022, 1, 1),
                ),
                state_entities.StateSentenceStatusSnapshot(
                    state_code=self.state_code,
                    status=StateSentenceStatus.REVOKED,
                    status_update_datetime=datetime(2022, 4, 1),
                ),
            ],
            person=self.state_person,
        )
        self.state_person.sentences.append(probation_sentence)
        parole_sentence = state_entities.StateSentence(
            state_code=self.state_code,
            external_id="SENT-EXTERNAL-4",
            sentence_type=StateSentenceType.PAROLE,
            imposed_date=date(2023, 1, 1),
            charges=[
                state_entities.StateChargeV2(
                    external_id="CHARGE",
                    state_code=self.state_code,
                    status=StateChargeV2Status.PRESENT_WITHOUT_INFO,
                )
            ],
            sentence_status_snapshots=[
                state_entities.StateSentenceStatusSnapshot(
                    state_code=self.state_code,
                    status=StateSentenceStatus.SERVING,
                    status_update_datetime=datetime(2023, 1, 1),
                ),
                state_entities.StateSentenceStatusSnapshot(
                    state_code=self.state_code,
                    status=StateSentenceStatus.REVOKED,
                    status_update_datetime=datetime(2023, 4, 1),
                ),
            ],
            person=self.state_person,
        )
        self.state_person.sentences.append(parole_sentence)
        errors = validate_root_entity(self.state_person, self.field_index)
        self.assertEqual(len(errors), 0)

    def test_revoked_sentence_status_check_invalid(self) -> None:
        state_prison_sentence = state_entities.StateSentence(
            state_code=self.state_code,
            external_id="SENT-EXTERNAL-2",
            sentence_type=StateSentenceType.STATE_PRISON,
            imposed_date=date(2022, 1, 1),
            charges=[
                state_entities.StateChargeV2(
                    external_id="CHARGE",
                    state_code=self.state_code,
                    status=StateChargeV2Status.PRESENT_WITHOUT_INFO,
                )
            ],
            sentence_status_snapshots=[
                state_entities.StateSentenceStatusSnapshot(
                    state_code=self.state_code,
                    status=StateSentenceStatus.SERVING,
                    status_update_datetime=datetime(2022, 1, 1),
                ),
                state_entities.StateSentenceStatusSnapshot(
                    state_code=self.state_code,
                    status=StateSentenceStatus.REVOKED,
                    status_update_datetime=datetime(2022, 4, 1),
                ),
                state_entities.StateSentenceStatusSnapshot(
                    state_code=self.state_code,
                    status=StateSentenceStatus.COMPLETED,
                    status_update_datetime=datetime(2022, 5, 1),
                ),
            ],
            person=self.state_person,
        )
        self.state_person.sentences.append(state_prison_sentence)
        errors = validate_root_entity(self.state_person, self.field_index)
        self.assertEqual(len(errors), 1)
        self.assertEqual(
            errors[0],
            (
                "Found person StatePerson(person_id=1, "
                "external_ids=[StatePersonExternalId(external_id='1', "
                "id_type='US_XX_TEST_PERSON', person_external_id_id=None)]) with REVOKED "
                "status on StateSentenceType.STATE_PRISON sentence. REVOKED statuses are only "
                "allowed on PROBATION and PAROLE type sentences."
            ),
        )

    def test_sequence_num_are_unique_for_each_sentence(self) -> None:
        probation_sentence = state_entities.StateSentence(
            state_code=self.state_code,
            external_id="SENT-EXTERNAL-1",
            sentence_type=StateSentenceType.PROBATION,
            imposed_date=date(2022, 1, 1),
            charges=[
                state_entities.StateChargeV2(
                    external_id="CHARGE",
                    state_code=self.state_code,
                    status=StateChargeV2Status.PRESENT_WITHOUT_INFO,
                )
            ],
            sentence_status_snapshots=[
                state_entities.StateSentenceStatusSnapshot(
                    sequence_num=1,
                    state_code=self.state_code,
                    status=StateSentenceStatus.SERVING,
                    status_update_datetime=datetime(2022, 1, 1),
                ),
                state_entities.StateSentenceStatusSnapshot(
                    sequence_num=2,
                    state_code=self.state_code,
                    status=StateSentenceStatus.REVOKED,
                    status_update_datetime=datetime(2022, 4, 1),
                ),
            ],
            person=self.state_person,
        )
        self.state_person.sentences.append(probation_sentence)
        incarceration_sentence = state_entities.StateSentence(
            state_code=self.state_code,
            external_id="SENT-EXTERNAL-2",
            sentence_type=StateSentenceType.PROBATION,
            imposed_date=date(2022, 1, 1),
            charges=[
                state_entities.StateChargeV2(
                    external_id="CHARGE",
                    state_code=self.state_code,
                    status=StateChargeV2Status.PRESENT_WITHOUT_INFO,
                )
            ],
            sentence_status_snapshots=[
                state_entities.StateSentenceStatusSnapshot(
                    sequence_num=1,
                    state_code=self.state_code,
                    status=StateSentenceStatus.SERVING,
                    status_update_datetime=datetime(2022, 1, 1),
                ),
                state_entities.StateSentenceStatusSnapshot(
                    sequence_num=2,
                    state_code=self.state_code,
                    status=StateSentenceStatus.REVOKED,
                    status_update_datetime=datetime(2022, 4, 1),
                ),
            ],
            person=self.state_person,
        )
        self.state_person.sentences.append(incarceration_sentence)
        errors = validate_root_entity(self.state_person, self.field_index)
        self.assertEqual(len(errors), 0)

    def test_sentence_to_sentence_group_reference(self) -> None:
        """Tests that StateSentenceGroup entities have a reference from a sentence."""
        self.state_person.sentence_groups.append(
            state_entities.StateSentenceGroup(
                state_code=self.state_code,
                external_id="TEST-SG",
            )
        )
        sentence = state_entities.StateSentence(
            state_code=self.state_code,
            external_id="SENT-EXTERNAL-1",
            sentence_group_external_id="TEST-SG",
            person=self.state_person,
            sentence_type=StateSentenceType.STATE_PRISON,
            imposed_date=date(2022, 1, 1),
            charges=[
                state_entities.StateChargeV2(
                    state_code=self.state_code,
                    external_id="CHARGE-EXTERNAL-1",
                    status=StateChargeV2Status.PRESENT_WITHOUT_INFO,
                )
            ],
        )
        self.state_person.sentences.append(sentence)
        errors = validate_root_entity(self.state_person, self.field_index)
        self.assertEqual(len(errors), 0)

        # Error when there is a SG but no sentence
        self.state_person.sentences = []
        errors = validate_root_entity(self.state_person, self.field_index)
        self.assertEqual(len(errors), 1)
        self.assertEqual(
            errors[0],
            "Found StateSentenceGroup TEST-SG without an associated sentence.",
        )

        # Error when there is a sentence but no SG (but at least one SG)
        sentence.sentence_group_external_id = "TEST-SG-2"
        self.state_person.sentences = [sentence]
        errors = validate_root_entity(self.state_person, self.field_index)
        self.assertEqual(len(errors), 2)
        self.assertEqual(
            errors[0],
            "Found sentence_ext_ids=['SENT-EXTERNAL-1'] referencing non-existent StateSentenceGroup TEST-SG-2.",
        )
        self.assertEqual(
            errors[1],
            "Found StateSentenceGroup TEST-SG without an associated sentence.",
        )

    def test_no_parole_possible_means_no_parole_projected_dates_group_level(
        self,
    ) -> None:
        """
        If all sentences in a sentence group have parole_possible=False,
        then there should be no parole related projected dates on all
        sentence_group_length entities.
        """
        # One sentence, parole_possible is None - no Error
        sentence = state_entities.StateSentence(
            state_code=self.state_code,
            external_id="SENT-EXTERNAL-1",
            sentence_group_external_id="SG-EXTERNAL-1",
            person=self.state_person,
            sentence_type=StateSentenceType.STATE_PRISON,
            imposed_date=date(2022, 1, 1),
            parole_possible=None,
            charges=[
                state_entities.StateChargeV2(
                    external_id="CHARGE",
                    state_code=self.state_code,
                    status=StateChargeV2Status.PRESENT_WITHOUT_INFO,
                )
            ],
        )
        group = state_entities.StateSentenceGroup(
            state_code=self.state_code,
            external_id="SG-EXTERNAL-1",
            sentence_group_lengths=[
                state_entities.StateSentenceGroupLength(
                    state_code=self.state_code,
                    group_update_datetime=datetime(2022, 1, 1),
                    parole_eligibility_date_external=date(2025, 1, 1),
                ),
            ],
        )
        self.state_person.sentences = [sentence]
        self.state_person.sentence_groups = [group]
        errors = validate_root_entity(self.state_person, self.field_index)
        self.assertEqual(errors, [])

        # One sentence, parole_possible is False - Expected Error
        sentence = state_entities.StateSentence(
            state_code=self.state_code,
            external_id="SENT-EXTERNAL-1",
            sentence_group_external_id="SG-EXTERNAL-1",
            person=self.state_person,
            sentence_type=StateSentenceType.STATE_PRISON,
            imposed_date=date(2022, 1, 1),
            parole_possible=False,
            charges=[
                state_entities.StateChargeV2(
                    external_id="CHARGE",
                    state_code=self.state_code,
                    status=StateChargeV2Status.PRESENT_WITHOUT_INFO,
                )
            ],
        )
        self.state_person.sentences = [sentence]
        self.state_person.sentence_groups = [group]
        errors = validate_root_entity(self.state_person, self.field_index)
        self.assertEqual(
            errors,
            [
                "StateSentenceGroup(external_id='SG-EXTERNAL-1', sentence_group_id=None) "
                "has parole eligibility date, but none of its sentences allow parole."
            ],
        )

        # Mutliple sentences, parole_possible is False - Expected Error
        sentence_1 = state_entities.StateSentence(
            state_code=self.state_code,
            external_id="SENT-EXTERNAL-1",
            sentence_group_external_id="SG-EXTERNAL-1",
            person=self.state_person,
            sentence_type=StateSentenceType.STATE_PRISON,
            imposed_date=date(2022, 1, 1),
            parole_possible=False,
            charges=[
                state_entities.StateChargeV2(
                    external_id="CHARGE",
                    state_code=self.state_code,
                    status=StateChargeV2Status.PRESENT_WITHOUT_INFO,
                )
            ],
        )
        sentence_2 = state_entities.StateSentence(
            state_code=self.state_code,
            external_id="SENT-EXTERNAL-2",
            sentence_group_external_id="SG-EXTERNAL-1",
            person=self.state_person,
            sentence_type=StateSentenceType.STATE_PRISON,
            imposed_date=date(2022, 1, 1),
            parole_possible=False,
            charges=[
                state_entities.StateChargeV2(
                    external_id="CHARGE",
                    state_code=self.state_code,
                    status=StateChargeV2Status.PRESENT_WITHOUT_INFO,
                )
            ],
        )
        self.state_person.sentences = [sentence_1, sentence_2]
        self.state_person.sentence_groups = [group]
        errors = validate_root_entity(self.state_person, self.field_index)
        self.assertEqual(
            errors,
            [
                "StateSentenceGroup(external_id='SG-EXTERNAL-1', sentence_group_id=None) "
                "has parole eligibility date, but none of its sentences allow parole."
            ],
        )

        # Mutliple sentences, parole_possible is True or None - No Error
        sentence_1 = state_entities.StateSentence(
            state_code=self.state_code,
            external_id="SENT-EXTERNAL-1",
            sentence_group_external_id="SG-EXTERNAL-1",
            person=self.state_person,
            sentence_type=StateSentenceType.STATE_PRISON,
            imposed_date=date(2022, 1, 1),
            parole_possible=None,
            charges=[
                state_entities.StateChargeV2(
                    external_id="CHARGE",
                    state_code=self.state_code,
                    status=StateChargeV2Status.PRESENT_WITHOUT_INFO,
                )
            ],
        )
        sentence_2 = state_entities.StateSentence(
            state_code=self.state_code,
            external_id="SENT-EXTERNAL-2",
            sentence_group_external_id="SG-EXTERNAL-1",
            person=self.state_person,
            sentence_type=StateSentenceType.STATE_PRISON,
            imposed_date=date(2022, 1, 1),
            parole_possible=True,
            charges=[
                state_entities.StateChargeV2(
                    external_id="CHARGE",
                    state_code=self.state_code,
                    status=StateChargeV2Status.PRESENT_WITHOUT_INFO,
                )
            ],
        )
        self.state_person.sentences = [sentence_1, sentence_2]
        self.state_person.sentence_groups = [group]
        errors = validate_root_entity(self.state_person, self.field_index)
        self.assertEqual(errors, [])
