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
"""Tests for utils/extractor_utils.py."""
# pylint: disable=protected-access
import datetime
import unittest
from datetime import date
from typing import List
from unittest.mock import MagicMock

import apache_beam as beam
import attr
from apache_beam.testing.test_pipeline import TestPipeline
from apache_beam.testing.util import assert_that, equal_to
from mock import patch

from recidiviz.big_query.big_query_query_provider import SimpleBigQueryQueryProvider
from recidiviz.calculator.query.state.views.reference.persons_to_recent_county_of_residence import (
    PERSONS_TO_RECENT_COUNTY_OF_RESIDENCE_VIEW_BUILDER,
    PERSONS_TO_RECENT_COUNTY_OF_RESIDENCE_VIEW_NAME,
)
from recidiviz.common.constants.state.state_assessment import (
    StateAssessmentClass,
    StateAssessmentType,
)
from recidiviz.common.constants.state.state_person import (
    StateEthnicity,
    StateGender,
    StateRace,
    StateResidencyStatus,
)
from recidiviz.common.constants.state.state_program_assignment import (
    StateProgramAssignmentParticipationStatus,
)
from recidiviz.common.constants.states import StateCode
from recidiviz.persistence.database.schema.state import schema
from recidiviz.persistence.database.schema_entity_converter.state.schema_entity_converter import (
    StateSchemaToEntityConverter,
)
from recidiviz.persistence.entity import entity_utils
from recidiviz.persistence.entity.state import entities, normalized_entities
from recidiviz.pipelines.utils.beam_utils import extractor_utils
from recidiviz.tests.persistence.database import database_test_utils
from recidiviz.tests.pipelines.calculator_test_utils import (
    normalized_database_base_dict,
    normalized_database_base_dict_list,
    remove_relationship_properties,
)
from recidiviz.tests.pipelines.fake_bigquery import (
    FakeReadFromBigQuery,
    FakeReadFromBigQueryFactory,
)
from recidiviz.tests.pipelines.utils.run_pipeline_test_utils import (
    default_data_dict_for_root_schema_classes,
)


class TestExtractDataForPipeline(unittest.TestCase):
    """Tests the ExtractDataForPipeline PTransform."""

    def setUp(self) -> None:
        self.fake_bq_source_factory = FakeReadFromBigQueryFactory()

    def testExtractDataForPipeline(self):
        """Tests the extraction of multiple entities with cross-entity
        relationship properties hydrated."""

        person_id = 12345

        schema_person = schema.StatePerson(
            person_id=person_id,
            current_address="123 Street",
            full_name="Bernard Madoff",
            birthdate=date(1970, 1, 1),
            gender=StateGender.MALE,
            residency_status=StateResidencyStatus.PERMANENT,
            state_code="US_XX",
        )

        schema_person_data = [normalized_database_base_dict(schema_person)]

        schema_ethnicity = schema.StatePersonEthnicity(
            state_code="US_XX",
            ethnicity=StateEthnicity.NOT_HISPANIC,
            person_id=person_id,
            person_ethnicity_id=234,
        )

        ethnicities_data = [normalized_database_base_dict(schema_ethnicity)]

        schema_alias = schema.StatePersonAlias(
            state_code="US_XX",
            full_name="Bernie Madoff",
            person_alias_id=18615,
            person_id=person_id,
        )

        alias_data = [normalized_database_base_dict(schema_alias)]

        schema_external_id = schema.StatePersonExternalId(
            person_external_id_id=999,
            external_id="888",
            state_code="US_XX",
            id_type="US_XX_TYPE",
            person_id=person_id,
        )

        external_ids_data = [normalized_database_base_dict(schema_external_id)]

        schema_race_1 = schema.StatePersonRace(
            race=StateRace.WHITE, state_code="US_XX", person_id=person_id
        )

        schema_race_2 = schema.StatePersonRace(
            race=StateRace.BLACK, state_code="US_XX", person_id=person_id
        )

        races_data = [
            normalized_database_base_dict(schema_race_1),
            normalized_database_base_dict(schema_race_2),
        ]

        schema_assessment = schema.StateAssessment(
            external_id="a1",
            assessment_class=StateAssessmentClass.RISK,
            assessment_type=StateAssessmentType.LSIR,
            assessment_date=date(2012, 4, 1),
            state_code="US_XX",
            assessment_score=29,
            assessment_id=184672,
            person_id=person_id,
        )

        assessment_data = [normalized_database_base_dict(schema_assessment)]
        data_dict = default_data_dict_for_root_schema_classes([schema.StatePerson])

        data_dict_overrides = {
            schema.StatePerson.__tablename__: schema_person_data,
            schema.StatePersonEthnicity.__tablename__: ethnicities_data,
            schema.StatePersonAlias.__tablename__: alias_data,
            schema.StatePersonExternalId.__tablename__: external_ids_data,
            schema.StateAssessment.__tablename__: assessment_data,
            schema.StatePersonRace.__tablename__: races_data,
        }
        data_dict.update(data_dict_overrides)

        entity_converter = StateSchemaToEntityConverter()

        entity_person = entity_converter.convert(schema_person)
        entity_ethnicity = entity_converter.convert(schema_ethnicity)
        entity_alias = entity_converter.convert(schema_alias)
        entity_external_id = entity_converter.convert(schema_external_id)
        entity_races = entity_converter.convert_all([schema_race_1, schema_race_2])
        entity_assessment = entity_converter.convert(schema_assessment)

        entity_person.ethnicities = [entity_ethnicity]
        entity_person.aliases = [entity_alias]
        entity_person.external_ids = [entity_external_id]
        entity_person.races = entity_races
        entity_person.assessments = [entity_assessment]

        project = "project"
        dataset = "state"

        with patch(
            "apache_beam.io.ReadFromBigQuery",
            self.fake_bq_source_factory.create_fake_bq_source_constructor(
                expected_entities_dataset=dataset, data_dict=data_dict
            ),
        ):
            test_pipeline = TestPipeline()

            output = test_pipeline | extractor_utils.ExtractRootEntityDataForPipeline(
                state_code=StateCode(schema_person.state_code),
                project_id=project,
                entities_dataset=dataset,
                required_entity_classes=[
                    entities.StatePerson,
                    entities.StatePersonRace,
                    entities.StatePersonEthnicity,
                    entities.StatePersonAlias,
                    entities.StatePersonExternalId,
                    entities.StateAssessment,
                ],
                reference_data_queries_by_name={},
                root_entity_cls=entities.StatePerson,
                root_entity_id_filter_set=None,
            )

            assert_that(
                output,
                equal_to(
                    [
                        (
                            12345,
                            {
                                entities.StatePerson.__name__: [entity_person],
                                entities.StatePersonRace.__name__: entity_races,
                                entities.StatePersonEthnicity.__name__: [
                                    entity_ethnicity
                                ],
                                entities.StatePersonAlias.__name__: [entity_alias],
                                entities.StatePersonExternalId.__name__: [
                                    entity_external_id
                                ],
                                entities.StateAssessment.__name__: [entity_assessment],
                            },
                        )
                    ]
                ),
            )

            test_pipeline.run()

    def testExtractDataForPipeline_withManyRelationshipTypes(self):
        """Tests the extraction of multiple entities with cross-entity
        relationship properties hydrated."""
        required_schema_classes = [
            schema.StatePerson,
            schema.StateSupervisionViolation,
            schema.StateSupervisionViolationTypeEntry,
            schema.StateSupervisionViolatedConditionEntry,
            schema.StateSupervisionViolationResponse,
            schema.StateSupervisionViolationResponseDecisionEntry,
        ]

        person_id = 12345

        schema_person = schema.StatePerson(
            person_id=person_id,
            current_address="123 Street",
            full_name="Bernard Madoff",
            birthdate=date(1970, 1, 1),
            gender=StateGender.MALE,
            residency_status=StateResidencyStatus.PERMANENT,
            state_code="US_XX",
        )

        schema_violation_decision = database_test_utils.generate_test_supervision_violation_response_decision_entry(
            person_id
        )

        schema_violation_response = (
            database_test_utils.generate_test_supervision_violation_response(
                person_id, decisions=[schema_violation_decision]
            )
        )

        schema_supervision_violation = (
            database_test_utils.generate_test_supervision_violation(
                person_id, supervision_violation_responses=[schema_violation_response]
            )
        )
        schema_violation_response.supervision_violation_id = (
            schema_supervision_violation.supervision_violation_id
        )
        for (
            decision
        ) in schema_violation_response.supervision_violation_response_decisions:
            decision.supervision_violation_response_id = (
                schema_violation_response.supervision_violation_response_id
            )
        schema_person.supervision_violations = [schema_supervision_violation]

        person_data = [normalized_database_base_dict(schema_person)]
        supervision_violation_data = [
            normalized_database_base_dict(schema_supervision_violation)
        ]
        supervision_violation_type_entry_data = normalized_database_base_dict_list(
            schema_supervision_violation.supervision_violation_types
        )
        supervision_violation_condition_entry_data = normalized_database_base_dict_list(
            schema_supervision_violation.supervision_violated_conditions
        )
        supervision_violation_response_data = [
            normalized_database_base_dict(schema_violation_response)
        ]
        supervision_violation_response_decision_data = (
            normalized_database_base_dict_list(
                schema_violation_response.supervision_violation_response_decisions
            )
        )

        data_dict = default_data_dict_for_root_schema_classes(required_schema_classes)

        data_dict_overrides = {
            schema.StatePerson.__tablename__: person_data,
            schema.StateSupervisionViolation.__tablename__: supervision_violation_data,
            schema.StateSupervisionViolationTypeEntry.__tablename__: supervision_violation_type_entry_data,
            schema.StateSupervisionViolatedConditionEntry.__tablename__: supervision_violation_condition_entry_data,
            schema.StateSupervisionViolationResponse.__tablename__: supervision_violation_response_data,
            schema.StateSupervisionViolationResponseDecisionEntry.__tablename__: supervision_violation_response_decision_data,
        }
        data_dict.update(data_dict_overrides)

        entity_converter = StateSchemaToEntityConverter()

        entity_person = entity_converter.convert(schema_person)
        entity_violation: entities.StateSupervisionViolation = entity_converter.convert(
            schema_supervision_violation
        )
        entity_violation_response = entity_violation.supervision_violation_responses[0]
        entity_violation_types = entity_violation.supervision_violation_types
        entity_violated_conditions = entity_violation.supervision_violated_conditions
        entity_violation_response_decisions = (
            entity_violation_response.supervision_violation_response_decisions
        )

        all_non_person_entities = [
            entity_violation,
            entity_violation_response,
        ]

        all_non_person_entities.extend(entity_violation_types)
        all_non_person_entities.extend(entity_violated_conditions)
        all_non_person_entities.extend(entity_violation_response_decisions)

        # The entity converter sets the person field, but we don't hydrate this
        # relationship
        for entity in all_non_person_entities:
            setattr(entity, "person", None)

        project = "project"
        dataset = "state"

        with patch(
            "apache_beam.io.ReadFromBigQuery",
            self.fake_bq_source_factory.create_fake_bq_source_constructor(
                expected_entities_dataset=dataset, data_dict=data_dict
            ),
        ):
            test_pipeline = TestPipeline()

            output = test_pipeline | extractor_utils.ExtractRootEntityDataForPipeline(
                state_code=StateCode(entity_person.state_code),
                project_id=project,
                entities_dataset=dataset,
                required_entity_classes=[
                    entities.StatePerson,
                    entities.StateSupervisionViolation,
                    entities.StateSupervisionViolationResponse,
                    entities.StateSupervisionViolationTypeEntry,
                    entities.StateSupervisionViolatedConditionEntry,
                    entities.StateSupervisionViolationResponseDecisionEntry,
                ],
                reference_data_queries_by_name={},
                root_entity_cls=entities.StatePerson,
                root_entity_id_filter_set=None,
            )

            assert_that(
                output,
                equal_to(
                    [
                        (
                            12345,
                            {
                                entities.StatePerson.__name__: [entity_person],
                                entities.StateSupervisionViolation.__name__: [
                                    entity_violation
                                ],
                                entities.StateSupervisionViolationResponse.__name__: [
                                    entity_violation_response
                                ],
                                entities.StateSupervisionViolationTypeEntry.__name__: entity_violation_types,
                                entities.StateSupervisionViolatedConditionEntry.__name__: entity_violated_conditions,
                                entities.StateSupervisionViolationResponseDecisionEntry.__name__: entity_violation_response_decisions,
                            },
                        )
                    ]
                ),
            )

            test_pipeline.run()

    def testExtractDataForPipeline_RootEntityClassNotIncluded(self):
        """Tests the extraction of multiple entities, where the root entity class is
        not a class that's included in the list of required entities."""

        person_id = 12345

        schema_ethnicity = schema.StatePersonEthnicity(
            state_code="US_XX",
            ethnicity=StateEthnicity.NOT_HISPANIC,
            person_id=person_id,
            person_ethnicity_id=234,
        )

        ethnicities_data = [normalized_database_base_dict(schema_ethnicity)]

        schema_alias = schema.StatePersonAlias(
            state_code="US_XX",
            full_name="Bernie Madoff",
            person_alias_id=18615,
            person_id=person_id,
        )

        alias_data = [normalized_database_base_dict(schema_alias)]

        schema_external_id = schema.StatePersonExternalId(
            person_external_id_id=999,
            external_id="888",
            state_code="US_XX",
            id_type="US_XX_TYPE",
            person_id=person_id,
        )

        external_ids_data = [normalized_database_base_dict(schema_external_id)]

        schema_race_1 = schema.StatePersonRace(
            race=StateRace.WHITE, state_code="US_XX", person_id=person_id
        )

        schema_race_2 = schema.StatePersonRace(
            race=StateRace.BLACK, state_code="US_XX", person_id=person_id
        )

        races_data = [
            normalized_database_base_dict(schema_race_1),
            normalized_database_base_dict(schema_race_2),
        ]

        schema_assessment = schema.StateAssessment(
            external_id="a1",
            assessment_class=StateAssessmentClass.RISK,
            assessment_type=StateAssessmentType.LSIR,
            assessment_date=date(2012, 4, 1),
            state_code="US_XX",
            assessment_score=29,
            assessment_id=184672,
            person_id=person_id,
        )

        assessment_data = [normalized_database_base_dict(schema_assessment)]
        data_dict = default_data_dict_for_root_schema_classes([schema.StatePerson])

        data_dict_overrides = {
            schema.StatePersonEthnicity.__tablename__: ethnicities_data,
            schema.StatePersonAlias.__tablename__: alias_data,
            schema.StatePersonExternalId.__tablename__: external_ids_data,
            schema.StateAssessment.__tablename__: assessment_data,
            schema.StatePersonRace.__tablename__: races_data,
        }
        data_dict.update(data_dict_overrides)

        entity_converter = StateSchemaToEntityConverter()

        entity_ethnicity = entity_converter.convert(schema_ethnicity)
        entity_alias = entity_converter.convert(schema_alias)
        entity_external_id = entity_converter.convert(schema_external_id)
        entity_races = entity_converter.convert_all([schema_race_1, schema_race_2])
        entity_assessment = entity_converter.convert(schema_assessment)

        project = "project"
        dataset = "state"

        with patch(
            "apache_beam.io.ReadFromBigQuery",
            self.fake_bq_source_factory.create_fake_bq_source_constructor(
                expected_entities_dataset=dataset, data_dict=data_dict
            ),
        ):
            test_pipeline = TestPipeline()

            output = test_pipeline | extractor_utils.ExtractRootEntityDataForPipeline(
                state_code=StateCode.US_XX,
                project_id=project,
                entities_dataset=dataset,
                required_entity_classes=[
                    entities.StatePersonRace,
                    entities.StatePersonEthnicity,
                    entities.StatePersonAlias,
                    entities.StatePersonExternalId,
                    entities.StateAssessment,
                ],
                reference_data_queries_by_name={},
                root_entity_cls=entities.StatePerson,
                root_entity_id_filter_set=None,
            )

            assert_that(
                output,
                equal_to(
                    [
                        (
                            12345,
                            {
                                entities.StatePersonRace.__name__: entity_races,
                                entities.StatePersonEthnicity.__name__: [
                                    entity_ethnicity
                                ],
                                entities.StatePersonAlias.__name__: [entity_alias],
                                entities.StatePersonExternalId.__name__: [
                                    entity_external_id
                                ],
                                entities.StateAssessment.__name__: [entity_assessment],
                            },
                        )
                    ]
                ),
            )

            test_pipeline.run()

    def testExtractDataForPipeline_withAssociationTables(self):
        """Tests the extraction of multiple entities with cross-entity
        relationship properties hydrated."""
        required_schema_classes = [
            schema.StatePerson,
            schema.StateSupervisionSentence,
            schema.StateCharge,
        ]

        person_id = 12345

        schema_person = schema.StatePerson(
            person_id=person_id,
            current_address="123 Street",
            full_name="Bernard Madoff",
            birthdate=date(1970, 1, 1),
            gender=StateGender.MALE,
            residency_status=StateResidencyStatus.PERMANENT,
            state_code="US_XX",
        )

        schema_charge_1 = database_test_utils.generate_test_charge(
            person_id=person_id, charge_id=123
        )

        schema_charge_2 = database_test_utils.generate_test_charge(
            person_id=person_id, charge_id=456
        )

        schema_sentence = database_test_utils.generate_test_supervision_sentence(
            person_id=person_id,
            charges=[schema_charge_1, schema_charge_2],
            early_discharges=[],
        )

        person_data = [normalized_database_base_dict(schema_person)]
        charge_data = normalized_database_base_dict_list(
            [schema_charge_1, schema_charge_2]
        )
        sentence_data = [normalized_database_base_dict(schema_sentence)]

        state_charge_supervision_sentence_association_table_data = [
            {
                "charge_id": charge.charge_id,
                "supervision_sentence_id": schema_sentence.supervision_sentence_id,
            }
            for charge in [schema_charge_1, schema_charge_2]
        ]

        data_dict = default_data_dict_for_root_schema_classes(required_schema_classes)

        data_dict_overrides = {
            schema.StatePerson.__tablename__: person_data,
            schema.StateSupervisionSentence.__tablename__: sentence_data,
            schema.StateCharge.__tablename__: charge_data,
            schema.state_charge_supervision_sentence_association_table.name: state_charge_supervision_sentence_association_table_data,
        }
        data_dict.update(data_dict_overrides)

        entity_converter = StateSchemaToEntityConverter()

        entity_person = entity_converter.convert(schema_person)
        entity_charges: List[entities.StateCharge] = entity_converter.convert_all(
            [schema_charge_1, schema_charge_2], populate_back_edges=False
        )
        entity_sentence: entities.StateSupervisionSentence = entity_converter.convert(
            schema_sentence
        )

        entity_charges[0].supervision_sentences = [entity_sentence]
        entity_charges[1].supervision_sentences = [entity_sentence]
        entity_sentence.charges = entity_charges
        entity_person.supervision_sentences = [entity_sentence]

        project = "project"
        dataset = "state"

        with patch(
            "apache_beam.io.ReadFromBigQuery",
            self.fake_bq_source_factory.create_fake_bq_source_constructor(
                expected_entities_dataset=dataset, data_dict=data_dict
            ),
        ):
            test_pipeline = TestPipeline()

            output = test_pipeline | extractor_utils.ExtractRootEntityDataForPipeline(
                state_code=StateCode(entity_person.state_code),
                project_id=project,
                entities_dataset=dataset,
                required_entity_classes=[
                    entities.StatePerson,
                    entities.StateSupervisionSentence,
                    entities.StateCharge,
                ],
                reference_data_queries_by_name={},
                root_entity_cls=entities.StatePerson,
                root_entity_id_filter_set=None,
            )

            assert_that(
                output,
                equal_to(
                    [
                        (
                            12345,
                            {
                                entities.StatePerson.__name__: [entity_person],
                                entities.StateSupervisionSentence.__name__: [
                                    entity_sentence
                                ],
                                entities.StateCharge.__name__: entity_charges,
                            },
                        )
                    ]
                ),
            )

            test_pipeline.run()

    def testExtractDataForPipeline_withAssociationTables_multi_parent_types(self):
        """Tests the extraction of multiple entities with cross-entity
        relationship properties hydrated."""
        required_schema_classes = [
            schema.StatePerson,
            schema.StateSupervisionSentence,
            schema.StateIncarcerationSentence,
            schema.StateCharge,
        ]

        person_id = 12345

        schema_person = schema.StatePerson(
            person_id=person_id,
            current_address="123 Street",
            full_name="Bernard Madoff",
            birthdate=date(1970, 1, 1),
            gender=StateGender.MALE,
            residency_status=StateResidencyStatus.PERMANENT,
            state_code="US_XX",
        )

        schema_charge_1 = database_test_utils.generate_test_charge(
            person_id=person_id, charge_id=123
        )

        schema_sup_sentence = database_test_utils.generate_test_supervision_sentence(
            person_id=person_id,
            charges=[schema_charge_1],
            early_discharges=[],
        )

        schema_inc_sentence = database_test_utils.generate_test_incarceration_sentence(
            person_id=person_id,
            charges=[schema_charge_1],
            early_discharges=[],
        )

        person_data = [normalized_database_base_dict(schema_person)]
        charge_data = normalized_database_base_dict_list([schema_charge_1])
        sentence_data = [normalized_database_base_dict(schema_sup_sentence)]
        inc_sentence_data = [normalized_database_base_dict(schema_inc_sentence)]

        state_charge_supervision_sentence_association_table_data = [
            {
                "charge_id": charge.charge_id,
                "supervision_sentence_id": schema_sup_sentence.supervision_sentence_id,
            }
            for charge in [schema_charge_1]
        ]

        state_charge_incarceration_sentence_association_table_data = [
            {
                "charge_id": charge.charge_id,
                "incarceration_sentence_id": schema_inc_sentence.incarceration_sentence_id,
            }
            for charge in [schema_charge_1]
        ]

        data_dict = default_data_dict_for_root_schema_classes(required_schema_classes)

        data_dict_overrides = {
            schema.StatePerson.__tablename__: person_data,
            schema.StateSupervisionSentence.__tablename__: sentence_data,
            schema.StateIncarcerationSentence.__tablename__: inc_sentence_data,
            schema.StateCharge.__tablename__: charge_data,
            schema.state_charge_supervision_sentence_association_table.name: state_charge_supervision_sentence_association_table_data,
            schema.state_charge_incarceration_sentence_association_table.name: state_charge_incarceration_sentence_association_table_data,
        }
        data_dict.update(data_dict_overrides)

        entity_converter = StateSchemaToEntityConverter()

        entity_person = entity_converter.convert(schema_person)
        entity_charges: List[entities.StateCharge] = entity_converter.convert_all(
            [schema_charge_1], populate_back_edges=False
        )
        entity_inc_sentence: entities.StateIncarcerationSentence = (
            entity_converter.convert(schema_inc_sentence)
        )
        entity_sup_sentence: entities.StateSupervisionSentence = (
            entity_converter.convert(schema_sup_sentence)
        )

        entity_charges[0].supervision_sentences = [entity_sup_sentence]
        entity_charges[0].incarceration_sentences = [entity_inc_sentence]
        entity_sup_sentence.charges = entity_charges
        entity_inc_sentence.charges = entity_charges
        entity_person.supervision_sentences = [entity_sup_sentence]
        entity_person.incarceration_sentences = [entity_inc_sentence]

        project = "project"
        dataset = "state"

        with patch(
            "apache_beam.io.ReadFromBigQuery",
            self.fake_bq_source_factory.create_fake_bq_source_constructor(
                expected_entities_dataset=dataset, data_dict=data_dict
            ),
        ):
            test_pipeline = TestPipeline()

            output = test_pipeline | extractor_utils.ExtractRootEntityDataForPipeline(
                state_code=StateCode(entity_person.state_code),
                project_id=project,
                entities_dataset=dataset,
                required_entity_classes=[
                    entities.StatePerson,
                    entities.StateSupervisionSentence,
                    entities.StateIncarcerationSentence,
                    entities.StateCharge,
                ],
                reference_data_queries_by_name={},
                root_entity_cls=entities.StatePerson,
                root_entity_id_filter_set=None,
            )

            print(
                [
                    (
                        12345,
                        {
                            entities.StatePerson.__name__: [entity_person],
                            entities.StateSupervisionSentence.__name__: [
                                entity_sup_sentence
                            ],
                            entities.StateIncarcerationSentence.__name__: [
                                entity_inc_sentence
                            ],
                            entities.StateCharge.__name__: entity_charges,
                        },
                    )
                ]
            )

            assert_that(
                output,
                equal_to(
                    [
                        (
                            12345,
                            {
                                entities.StatePerson.__name__: [entity_person],
                                entities.StateSupervisionSentence.__name__: [
                                    entity_sup_sentence
                                ],
                                entities.StateIncarcerationSentence.__name__: [
                                    entity_inc_sentence
                                ],
                                entities.StateCharge.__name__: entity_charges,
                            },
                        )
                    ]
                ),
            )

            test_pipeline.run()

    @patch(
        "recidiviz.utils.metadata.project_id", MagicMock(return_value="test-project")
    )
    def testExtractDataForPipeline_withReferenceTables(self):
        """Tests the extraction of multiple entities with cross-entity
        relationship properties hydrated."""

        person_id = 12345

        schema_person = schema.StatePerson(
            person_id=person_id,
            current_address="123 Street",
            full_name="Bernard Madoff",
            birthdate=date(1970, 1, 1),
            gender=StateGender.MALE,
            residency_status=StateResidencyStatus.PERMANENT,
            state_code="US_XX",
        )

        schema_person_data = [normalized_database_base_dict(schema_person)]

        schema_ethnicity = schema.StatePersonEthnicity(
            state_code="US_XX",
            ethnicity=StateEthnicity.NOT_HISPANIC,
            person_id=person_id,
            person_ethnicity_id=234,
        )

        ethnicities_data = [normalized_database_base_dict(schema_ethnicity)]

        schema_alias = schema.StatePersonAlias(
            state_code="US_XX",
            full_name="Bernie Madoff",
            person_alias_id=18615,
            person_id=person_id,
        )

        alias_data = [normalized_database_base_dict(schema_alias)]

        schema_external_id = schema.StatePersonExternalId(
            person_external_id_id=999,
            external_id="888",
            state_code="US_XX",
            id_type="US_XX_TYPE",
            person_id=person_id,
        )

        external_ids_data = [normalized_database_base_dict(schema_external_id)]

        schema_race_1 = schema.StatePersonRace(
            race=StateRace.WHITE, state_code="US_XX", person_id=person_id
        )

        schema_race_2 = schema.StatePersonRace(
            race=StateRace.BLACK, state_code="US_XX", person_id=person_id
        )

        races_data = [
            normalized_database_base_dict(schema_race_1),
            normalized_database_base_dict(schema_race_2),
        ]

        schema_assessment = schema.StateAssessment(
            external_id="a1",
            assessment_class=StateAssessmentClass.RISK,
            assessment_type=StateAssessmentType.LSIR,
            assessment_date=date(2012, 4, 1),
            state_code="US_XX",
            assessment_score=29,
            assessment_id=184672,
            person_id=person_id,
        )

        person_to_county_of_residence_data = [
            {
                "state_code": "US_XX",
                "person_id": person_id,
                "county_of_residence": "COUNTY",
            }
        ]

        assessment_data = [normalized_database_base_dict(schema_assessment)]
        data_dict = default_data_dict_for_root_schema_classes([schema.StatePerson])

        data_dict_overrides = {
            schema.StatePerson.__tablename__: schema_person_data,
            schema.StatePersonEthnicity.__tablename__: ethnicities_data,
            schema.StatePersonAlias.__tablename__: alias_data,
            schema.StatePersonExternalId.__tablename__: external_ids_data,
            schema.StateAssessment.__tablename__: assessment_data,
            schema.StatePersonRace.__tablename__: races_data,
            PERSONS_TO_RECENT_COUNTY_OF_RESIDENCE_VIEW_NAME: person_to_county_of_residence_data,
        }
        data_dict.update(data_dict_overrides)

        entity_converter = StateSchemaToEntityConverter()

        entity_person = entity_converter.convert(schema_person)
        entity_ethnicity = entity_converter.convert(schema_ethnicity)
        entity_alias = entity_converter.convert(schema_alias)
        entity_external_id = entity_converter.convert(schema_external_id)
        entity_races = entity_converter.convert_all([schema_race_1, schema_race_2])
        entity_assessment = entity_converter.convert(schema_assessment)

        entity_person.ethnicities = [entity_ethnicity]
        entity_person.aliases = [entity_alias]
        entity_person.external_ids = [entity_external_id]
        entity_person.races = entity_races
        entity_person.assessments = [entity_assessment]

        project = "project"
        dataset = "state"

        with patch(
            "apache_beam.io.ReadFromBigQuery",
            self.fake_bq_source_factory.create_fake_bq_source_constructor(
                expected_entities_dataset=dataset, data_dict=data_dict
            ),
        ):
            test_pipeline = TestPipeline()

            output = test_pipeline | extractor_utils.ExtractRootEntityDataForPipeline(
                state_code=StateCode(schema_person.state_code),
                project_id=project,
                entities_dataset=dataset,
                required_entity_classes=[
                    entities.StatePerson,
                    entities.StatePersonRace,
                    entities.StatePersonEthnicity,
                    entities.StatePersonAlias,
                    entities.StatePersonExternalId,
                    entities.StateAssessment,
                ],
                reference_data_queries_by_name={
                    PERSONS_TO_RECENT_COUNTY_OF_RESIDENCE_VIEW_NAME: SimpleBigQueryQueryProvider(
                        PERSONS_TO_RECENT_COUNTY_OF_RESIDENCE_VIEW_BUILDER.build(
                            address_overrides=None
                        ).view_query
                    )
                },
                root_entity_cls=entities.StatePerson,
                root_entity_id_filter_set=None,
            )

            assert_that(
                output,
                equal_to(
                    [
                        (
                            12345,
                            {
                                entities.StatePerson.__name__: [entity_person],
                                entities.StatePersonRace.__name__: entity_races,
                                entities.StatePersonEthnicity.__name__: [
                                    entity_ethnicity
                                ],
                                entities.StatePersonAlias.__name__: [entity_alias],
                                entities.StatePersonExternalId.__name__: [
                                    entity_external_id
                                ],
                                entities.StateAssessment.__name__: [entity_assessment],
                                PERSONS_TO_RECENT_COUNTY_OF_RESIDENCE_VIEW_NAME: person_to_county_of_residence_data,
                            },
                        )
                    ]
                ),
            )

            test_pipeline.run()

    def testExtractDataForPipeline_withAssociationTablesAndFilter(self):
        """Tests the extraction of multiple entities with cross-entity
        relationship properties hydrated, where there are required association
        tables, and a root_entity_id_field filter is set."""
        required_schema_classes = [
            schema.StatePerson,
            schema.StateSupervisionSentence,
            schema.StateCharge,
        ]

        person_id_1 = 12345

        schema_person_1 = schema.StatePerson(
            person_id=person_id_1,
            current_address="123 Street",
            full_name="Bernard Madoff",
            birthdate=date(1970, 1, 1),
            gender=StateGender.MALE,
            residency_status=StateResidencyStatus.PERMANENT,
            state_code="US_XX",
        )

        schema_charge_1 = database_test_utils.generate_test_charge(
            person_id=person_id_1, charge_id=123
        )

        schema_charge_2 = database_test_utils.generate_test_charge(
            person_id=person_id_1, charge_id=456
        )

        schema_sentence_1 = database_test_utils.generate_test_supervision_sentence(
            person_id=person_id_1,
            charges=[schema_charge_1, schema_charge_2],
            early_discharges=[],
        )

        person_id_2 = 67890

        schema_person_2 = schema.StatePerson(
            person_id=person_id_2,
            current_address="890 Street",
            full_name="Steven Steven",
            birthdate=date(1970, 1, 1),
            gender=StateGender.MALE,
            residency_status=StateResidencyStatus.PERMANENT,
            state_code="US_XX",
        )

        schema_charge_3 = database_test_utils.generate_test_charge(
            person_id=person_id_2, charge_id=789
        )

        schema_charge_4 = database_test_utils.generate_test_charge(
            person_id=person_id_2, charge_id=890
        )

        schema_sentence_2 = database_test_utils.generate_test_supervision_sentence(
            person_id=person_id_2,
            charges=[schema_charge_2, schema_charge_4],
            early_discharges=[],
        )

        schema_sentence_2.supervision_sentence_id = 2222

        person_data = normalized_database_base_dict_list(
            [schema_person_1, schema_person_2]
        )
        charge_data = normalized_database_base_dict_list(
            [schema_charge_1, schema_charge_2, schema_charge_3, schema_charge_4]
        )
        sentence_data = normalized_database_base_dict_list(
            [schema_sentence_1, schema_sentence_2]
        )

        state_charge_supervision_sentence_association_table_data = [
            {
                "charge_id": charge.charge_id,
                "supervision_sentence_id": schema_sentence_1.supervision_sentence_id,
            }
            for charge in [schema_charge_1, schema_charge_2]
        ] + [
            {
                "charge_id": charge.charge_id,
                "supervision_sentence_id": schema_sentence_2.supervision_sentence_id,
            }
            for charge in [schema_charge_3, schema_charge_4]
        ]

        data_dict = default_data_dict_for_root_schema_classes(required_schema_classes)

        data_dict_overrides = {
            schema.StatePerson.__tablename__: person_data,
            schema.StateSupervisionSentence.__tablename__: sentence_data,
            schema.StateCharge.__tablename__: charge_data,
            schema.state_charge_supervision_sentence_association_table.name: state_charge_supervision_sentence_association_table_data,
        }
        data_dict.update(data_dict_overrides)

        entity_converter = StateSchemaToEntityConverter()

        entity_person = entity_converter.convert(schema_person_1)
        entity_charges: List[entities.StateCharge] = entity_converter.convert_all(
            [schema_charge_1, schema_charge_2], populate_back_edges=False
        )
        entity_sentence: entities.StateSupervisionSentence = entity_converter.convert(
            schema_sentence_1
        )

        entity_charges[0].supervision_sentences = [entity_sentence]
        entity_charges[1].supervision_sentences = [entity_sentence]
        entity_sentence.charges = entity_charges
        entity_person.supervision_sentences = [entity_sentence]

        project = "project"
        dataset = "state"

        with patch(
            "apache_beam.io.ReadFromBigQuery",
            self.fake_bq_source_factory.create_fake_bq_source_constructor(
                expected_entities_dataset=dataset, data_dict=data_dict
            ),
        ):
            test_pipeline = TestPipeline()

            output = test_pipeline | extractor_utils.ExtractRootEntityDataForPipeline(
                state_code=StateCode(entity_person.state_code),
                project_id=project,
                entities_dataset=dataset,
                required_entity_classes=[
                    entities.StatePerson,
                    entities.StateSupervisionSentence,
                    entities.StateCharge,
                ],
                reference_data_queries_by_name={},
                root_entity_cls=entities.StatePerson,
                root_entity_id_filter_set={person_id_1},
            )

            assert_that(
                output,
                equal_to(
                    [
                        (
                            person_id_1,
                            {
                                entities.StatePerson.__name__: [entity_person],
                                entities.StateSupervisionSentence.__name__: [
                                    entity_sentence
                                ],
                                entities.StateCharge.__name__: entity_charges,
                            },
                        )
                    ]
                ),
            )

            test_pipeline.run()

    @patch(
        "recidiviz.utils.metadata.project_id", MagicMock(return_value="test-project")
    )
    def testExtractDataForPipeline_allows_for_empty_entities(self):
        person_id = 12345
        project = "project"
        dataset = "state"
        fields_of_test_reference = [
            {
                "person_id": person_id,
                "state_code": "US_XX",
                "agnt_note_title": "some_title",
            }
        ]

        data_dict = {
            PERSONS_TO_RECENT_COUNTY_OF_RESIDENCE_VIEW_NAME: fields_of_test_reference,
        }

        with patch(
            "apache_beam.io.ReadFromBigQuery",
            self.fake_bq_source_factory.create_fake_bq_source_constructor(
                expected_entities_dataset=dataset, data_dict=data_dict
            ),
        ):
            test_pipeline = TestPipeline()

            output = test_pipeline | extractor_utils.ExtractRootEntityDataForPipeline(
                state_code=StateCode.US_XX,
                project_id=project,
                entities_dataset=dataset,
                required_entity_classes=None,
                reference_data_queries_by_name={
                    PERSONS_TO_RECENT_COUNTY_OF_RESIDENCE_VIEW_NAME: SimpleBigQueryQueryProvider(
                        PERSONS_TO_RECENT_COUNTY_OF_RESIDENCE_VIEW_BUILDER.build(
                            address_overrides=None
                        ).view_query
                    )
                },
                root_entity_cls=entities.StatePerson,
                root_entity_id_filter_set=None,
            )

            assert_that(
                output,
                equal_to(
                    [
                        (
                            12345,
                            {
                                PERSONS_TO_RECENT_COUNTY_OF_RESIDENCE_VIEW_NAME: fields_of_test_reference,
                            },
                        )
                    ]
                ),
            )

            test_pipeline.run()

    def testExtractDataForPipeline_Normalized(self):
        """Tests the extraction of multiple entities with cross-entity
        relationship properties hydrated."""

        person_id = 12345

        schema_person = schema.StatePerson(
            person_id=person_id,
            current_address="123 Street",
            full_name="Bernard Madoff",
            birthdate=date(1970, 1, 1),
            gender=StateGender.MALE,
            residency_status=StateResidencyStatus.PERMANENT,
            state_code="US_XX",
        )

        schema_person_data = [normalized_database_base_dict(schema_person)]

        schema_ethnicity = schema.StatePersonEthnicity(
            state_code="US_XX",
            ethnicity=StateEthnicity.NOT_HISPANIC,
            person_id=person_id,
            person_ethnicity_id=234,
        )

        ethnicities_data = [normalized_database_base_dict(schema_ethnicity)]

        schema_alias = schema.StatePersonAlias(
            state_code="US_XX",
            full_name="Bernie Madoff",
            person_alias_id=18615,
            person_id=person_id,
        )

        alias_data = [normalized_database_base_dict(schema_alias)]

        schema_external_id = schema.StatePersonExternalId(
            person_external_id_id=999,
            external_id="888",
            state_code="US_XX",
            id_type="US_XX_TYPE",
            person_id=person_id,
        )

        external_ids_data = [normalized_database_base_dict(schema_external_id)]

        schema_race_1 = schema.StatePersonRace(
            race=StateRace.WHITE, state_code="US_XX", person_id=person_id
        )

        schema_race_2 = schema.StatePersonRace(
            race=StateRace.BLACK, state_code="US_XX", person_id=person_id
        )

        races_data = [
            normalized_database_base_dict(schema_race_1),
            normalized_database_base_dict(schema_race_2),
        ]

        schema_program_assignment = schema.StateProgramAssignment(
            state_code="US_XX",
            external_id="pa1",
            participation_status=StateProgramAssignmentParticipationStatus.IN_PROGRESS,
            person_id=person_id,
        )

        program_data = [
            normalized_database_base_dict(
                schema_program_assignment, {"sequence_num": 0}
            )
        ]
        data_dict = default_data_dict_for_root_schema_classes([schema.StatePerson])

        data_dict_overrides = {
            schema.StatePerson.__tablename__: schema_person_data,
            schema.StatePersonEthnicity.__tablename__: ethnicities_data,
            schema.StatePersonAlias.__tablename__: alias_data,
            schema.StatePersonExternalId.__tablename__: external_ids_data,
            schema.StateProgramAssignment.__tablename__: program_data,
            schema.StatePersonRace.__tablename__: races_data,
        }
        data_dict.update(data_dict_overrides)

        entity_converter = StateSchemaToEntityConverter()

        entity_person = entity_converter.convert(schema_person)
        entity_ethnicity = entity_converter.convert(schema_ethnicity)
        entity_alias = entity_converter.convert(schema_alias)
        entity_external_id = entity_converter.convert(schema_external_id)
        entity_races = entity_converter.convert_all([schema_race_1, schema_race_2])
        entity_program = normalized_entities.NormalizedStateProgramAssignment.new_with_defaults(
            state_code="US_XX",
            external_id="pa1",
            participation_status=StateProgramAssignmentParticipationStatus.IN_PROGRESS,
            sequence_num=0,
        )

        entity_person.ethnicities = [entity_ethnicity]
        entity_person.aliases = [entity_alias]
        entity_person.external_ids = [entity_external_id]
        entity_person.races = entity_races
        entity_person.program_assignments = [entity_program]

        project = "project"
        normalized_dataset = "us_xx_normalized_state"

        with patch(
            "apache_beam.io.ReadFromBigQuery",
            self.fake_bq_source_factory.create_fake_bq_source_constructor(
                expected_entities_dataset=normalized_dataset, data_dict=data_dict
            ),
        ):
            test_pipeline = TestPipeline()

            output = test_pipeline | extractor_utils.ExtractRootEntityDataForPipeline(
                state_code=StateCode(schema_person.state_code),
                project_id=project,
                entities_dataset=normalized_dataset,
                required_entity_classes=[
                    entities.StatePerson,
                    entities.StatePersonRace,
                    entities.StatePersonEthnicity,
                    entities.StatePersonAlias,
                    entities.StatePersonExternalId,
                    normalized_entities.NormalizedStateProgramAssignment,
                ],
                reference_data_queries_by_name={},
                root_entity_cls=entities.StatePerson,
                root_entity_id_filter_set=None,
            )

            assert_that(
                output,
                equal_to(
                    [
                        (
                            12345,
                            {
                                entities.StatePerson.__name__: [entity_person],
                                entities.StatePersonRace.__name__: entity_races,
                                entities.StatePersonEthnicity.__name__: [
                                    entity_ethnicity
                                ],
                                entities.StatePersonAlias.__name__: [entity_alias],
                                entities.StatePersonExternalId.__name__: [
                                    entity_external_id
                                ],
                                entities.StateProgramAssignment.__name__: [
                                    entity_program
                                ],
                            },
                        )
                    ]
                ),
            )

            test_pipeline.run()

    def testExtractDataForPipeline_withManyRelationshipTypes_Normalized(self):
        """Tests the extraction of multiple entities with cross-entity
        relationship properties hydrated."""
        required_schema_classes = [
            schema.StatePerson,
            schema.StateSupervisionViolation,
            schema.StateSupervisionViolationResponse,
        ]

        person_id = 12345

        schema_person = schema.StatePerson(
            person_id=person_id,
            current_address="123 Street",
            full_name="Bernard Madoff",
            birthdate=date(1970, 1, 1),
            gender=StateGender.MALE,
            residency_status=StateResidencyStatus.PERMANENT,
            state_code="US_XX",
        )

        schema_violation_response = (
            database_test_utils.generate_test_supervision_violation_response(
                person_id,
            )
        )

        schema_supervision_violation = (
            database_test_utils.generate_test_supervision_violation(
                person_id, supervision_violation_responses=[schema_violation_response]
            )
        )
        schema_violation_response.supervision_violation_id = (
            schema_supervision_violation.supervision_violation_id
        )

        schema_person.supervision_violations = [schema_supervision_violation]

        person_data = [normalized_database_base_dict(schema_person)]
        supervision_violation_data = [
            normalized_database_base_dict(schema_supervision_violation)
        ]

        supervision_violation_response_data = [
            normalized_database_base_dict(
                schema_violation_response, {"sequence_num": 0}
            ),
        ]

        data_dict = default_data_dict_for_root_schema_classes(required_schema_classes)

        data_dict_overrides = {
            schema.StatePerson.__tablename__: person_data,
            schema.StateSupervisionViolation.__tablename__: supervision_violation_data,
            schema.StateSupervisionViolationResponse.__tablename__: supervision_violation_response_data,
        }
        data_dict.update(data_dict_overrides)

        entity_converter = StateSchemaToEntityConverter()

        entity_person = entity_converter.convert(schema_person)
        entity_violation = (
            normalized_entities.NormalizedStateSupervisionViolation.new_with_defaults(
                supervision_violation_id=321,
                state_code="US_XX",
                external_id="external_id",
            )
        )
        entity_violation_response = normalized_entities.NormalizedStateSupervisionViolationResponse.new_with_defaults(
            supervision_violation_response_id=456,
            external_id="external_id",
            state_code="US_XX",
            response_date=datetime.date(2000, 1, 1),
            supervision_violation=entity_violation,
            sequence_num=0,
        )
        entity_person.supervision_violations = [entity_violation]
        entity_violation.supervision_violation_responses = [entity_violation_response]

        project = "project"
        normalized_dataset = "us_xx_normalized_state"

        with patch(
            "apache_beam.io.ReadFromBigQuery",
            self.fake_bq_source_factory.create_fake_bq_source_constructor(
                expected_entities_dataset=normalized_dataset, data_dict=data_dict
            ),
        ):
            test_pipeline = TestPipeline()

            output = test_pipeline | extractor_utils.ExtractRootEntityDataForPipeline(
                state_code=StateCode(entity_person.state_code),
                project_id=project,
                entities_dataset=normalized_dataset,
                required_entity_classes=[
                    entities.StatePerson,
                    normalized_entities.NormalizedStateSupervisionViolation,
                    normalized_entities.NormalizedStateSupervisionViolationResponse,
                ],
                reference_data_queries_by_name={},
                root_entity_cls=entities.StatePerson,
                root_entity_id_filter_set=None,
            )

            assert_that(
                output,
                equal_to(
                    [
                        (
                            12345,
                            {
                                entities.StatePerson.__name__: [entity_person],
                                entities.StateSupervisionViolation.__name__: [
                                    entity_violation
                                ],
                                entities.StateSupervisionViolationResponse.__name__: [
                                    entity_violation_response
                                ],
                            },
                        )
                    ]
                ),
            )

            test_pipeline.run()


class TestConnectHydratedRelatedEntities(unittest.TestCase):
    """Tests the _ConnectHydratedRelatedEntities DoFn."""

    def testConnectHydratedRelatedEntities(self) -> None:
        person_id = 123
        state_code = "US_XX"

        person = entities.StatePerson.new_with_defaults(
            person_id=person_id, state_code=state_code
        )

        person_race = entities.StatePersonRace.new_with_defaults(
            state_code=state_code, race=StateRace.WHITE
        )

        assessment = entities.StateAssessment.new_with_defaults(
            state_code=state_code,
            external_id="a1",
        )

        element = (
            person_id,
            {
                entities.StatePerson.__name__: [person],
                entities.StatePersonRace.__name__: [person_race],
                entities.StateAssessment.__name__: [assessment],
            },
        )

        output_person = attr.evolve(
            person,
        )
        output_race = attr.evolve(person_race, person=output_person)
        output_assessment = attr.evolve(assessment, person=output_person)
        output_person.races = [output_race]
        output_person.assessments = [output_assessment]

        correct_output = [
            (
                person_id,
                {
                    entities.StatePerson.__name__: [output_person],
                    entities.StatePersonRace.__name__: [output_race],
                    entities.StateAssessment.__name__: [output_assessment],
                },
            )
        ]

        relationships_to_hydrate = {
            entities.StatePerson.__name__: [
                extractor_utils.EntityRelationshipDetails(
                    property_name="races",
                    property_entity_class=entities.StatePersonRace,
                    is_forward_ref=True,
                    association_table=schema.StatePersonRace.__tablename__,
                    association_table_entity_id_field="person_race_id",
                ),
                extractor_utils.EntityRelationshipDetails(
                    property_name="assessments",
                    property_entity_class=entities.StateAssessment,
                    is_forward_ref=True,
                    association_table=schema.StateAssessment.__tablename__,
                    association_table_entity_id_field="assessment_id",
                ),
            ],
            entities.StatePersonRace.__name__: [
                extractor_utils.EntityRelationshipDetails(
                    property_name="person",
                    property_entity_class=entities.StatePerson,
                    is_forward_ref=False,
                    association_table=schema.StatePersonRace.__tablename__,
                    association_table_entity_id_field="person_id",
                )
            ],
            entities.StateAssessment.__name__: [
                extractor_utils.EntityRelationshipDetails(
                    property_name="person",
                    property_entity_class=entities.StatePerson,
                    is_forward_ref=False,
                    association_table=schema.StateAssessment.__tablename__,
                    association_table_entity_id_field="person_id",
                )
            ],
        }

        test_pipeline = TestPipeline()

        output = (
            test_pipeline
            | beam.Create([element])
            | "Connect related entities"
            >> beam.ParDo(
                extractor_utils._ConnectHydratedRelatedEntities(
                    root_entity_class=entities.StatePerson,
                    relationships_to_hydrate=relationships_to_hydrate,
                ),
            )
        )

        assert_that(output, equal_to(correct_output))

        test_pipeline.run()


class TestExtractAssociationValues(unittest.TestCase):
    """Tests the _ExtractAssociationValues DoFn."""

    def setUp(self) -> None:
        self.fake_bq_source_factory = FakeReadFromBigQueryFactory()

    def testExtractAssociationValues(self):
        """Tests extracting values required to associate two entities to each other."""
        charge = database_test_utils.generate_test_charge(person_id=123, charge_id=345)
        incarceration_sentence = (
            database_test_utils.generate_test_incarceration_sentence(person_id=123)
        )

        incarceration_sentence.charges = [charge]

        # Build association table for many-to-many relationship
        charge_sentence_association_table = [
            {
                "incarceration_sentence_id": incarceration_sentence.incarceration_sentence_id,
                "charge_id": charge.charge_id,
            }
        ]

        association_table_name = (
            schema.state_charge_incarceration_sentence_association_table.name
        )

        data_dict = {
            incarceration_sentence.__tablename__: [
                normalized_database_base_dict(incarceration_sentence)
            ],
            charge.__tablename__: [normalized_database_base_dict(charge)],
            association_table_name: charge_sentence_association_table,
        }

        project = "project"
        normalized_dataset = "us_xx_normalized_state"

        with patch(
            "apache_beam.io.ReadFromBigQuery",
            self.fake_bq_source_factory.create_fake_bq_source_constructor(
                expected_entities_dataset=normalized_dataset, data_dict=data_dict
            ),
        ):
            test_pipeline = TestPipeline()

            output = (
                test_pipeline
                | "Extract association table entities"
                >> extractor_utils._ExtractAssociationValues(
                    project_id=project,
                    entities_dataset=normalized_dataset,
                    entity_class=entities.StateIncarcerationSentence,
                    related_entity_class=entities.StateCharge,
                    related_id_field=entities.StateCharge.get_class_id_name(),
                    root_entity_id_field=entities.StatePerson.get_class_id_name(),
                    association_table=association_table_name,
                    root_entity_id_filter_set=None,
                    state_code=charge.state_code,
                )
            )

            assert_that(
                output,
                ExtractAssertMatchers.validate_extract_relationship_property_values(
                    root_entity_id=charge.person_id,
                    parent_id=incarceration_sentence.incarceration_sentence_id,
                    entity_id=charge.charge_id,
                ),
                label="Validate StateCharge output",
            )

            test_pipeline.run()


class TestExtractAllEntitiesOfType(unittest.TestCase):
    """Tests the ExtractAllEntitiesOfType PTransform."""

    def setUp(self) -> None:
        self.fake_bq_source_factory = FakeReadFromBigQueryFactory()

    def testExtractAllEntitiesOfType(self):
        person = remove_relationship_properties(
            database_test_utils.generate_test_person(
                person_id=123,
                state_code="US_XX",
                incarceration_incidents=[],
                supervision_violations=[],
                supervision_contacts=[],
                incarceration_sentences=[],
                supervision_sentences=[],
                incarceration_periods=[],
                supervision_periods=[],
            )
        )

        person_data = [normalized_database_base_dict(person)]

        data_dict = {person.__tablename__: person_data}

        output_person_entity = StateSchemaToEntityConverter().convert(person)

        entity_class = entity_utils.get_entity_class_in_module_with_name(
            entities, "StatePerson"
        )

        project = "project"
        normalized_dataset = "us_xx_normalized_state"

        with patch(
            "apache_beam.io.ReadFromBigQuery",
            self.fake_bq_source_factory.create_fake_bq_source_constructor(
                expected_entities_dataset=normalized_dataset, data_dict=data_dict
            ),
        ):
            test_pipeline = TestPipeline()

            output = (
                test_pipeline
                | "Extract StatePerson Entity"
                >> extractor_utils._ExtractAllEntitiesOfType(
                    project_id=project,
                    entities_dataset=normalized_dataset,
                    entity_class=entity_class,
                    root_entity_id_field=entity_class.get_class_id_name(),
                    root_entity_id_filter_set=None,
                    state_code=person.state_code,
                )
            )

            assert_that(
                output,
                equal_to([(output_person_entity.get_id(), output_person_entity)]),
            )

            test_pipeline.run()

    def testExtractAllEntitiesOfType_InvalidRootEntityIdField(self):
        person = remove_relationship_properties(
            database_test_utils.generate_test_person(
                person_id=123,
                state_code="US_XX",
                incarceration_incidents=[],
                supervision_violations=[],
                supervision_contacts=[],
                incarceration_sentences=[],
                supervision_sentences=[],
                incarceration_periods=[],
                supervision_periods=[],
            )
        )

        person_data = [normalized_database_base_dict(person)]

        data_dict = {person.__tablename__: person_data}

        entity_class = entity_utils.get_entity_class_in_module_with_name(
            entities, "StatePerson"
        )

        project = "project"
        dataset = "state"
        normalized_dataset = "us_xx_normalized_state"

        with patch(
            "apache_beam.io.ReadFromBigQuery",
            self.fake_bq_source_factory.create_fake_bq_source_constructor(
                expected_entities_dataset=dataset, data_dict=data_dict
            ),
        ):
            test_pipeline = TestPipeline()

            output = (
                test_pipeline
                | "Extract StatePerson Entity"
                >> extractor_utils._ExtractAllEntitiesOfType(
                    project_id=project,
                    entities_dataset=normalized_dataset,
                    entity_class=entity_class,
                    root_entity_id_field="XX",
                    root_entity_id_filter_set=None,
                    state_code="US_XX",
                )
            )

            assert_that(output, equal_to([]))

            test_pipeline.run()


class TestShallowHydrateEntity(unittest.TestCase):
    """Tests the ShallowHydrateEntity DoFn."""

    def testShallowHydrateEntity(self):
        """Tests hydrating a StateSupervisionViolation entity as the root
        entity."""
        supervision_violation = database_test_utils.generate_test_supervision_violation(
            123, []
        )

        supervision_violation_data = [
            normalized_database_base_dict(supervision_violation)
        ]

        supervision_violation = remove_relationship_properties(supervision_violation)

        output_violation_entity = StateSchemaToEntityConverter().convert(
            supervision_violation
        )

        entity_class = entity_utils.get_entity_class_in_module_with_name(
            entities, "StateSupervisionViolation"
        )

        test_pipeline = TestPipeline()

        # Read entities from data_dict
        entities_raw = (
            test_pipeline
            | "Read supervision violation data from dict"
            >> FakeReadFromBigQuery(table_values=supervision_violation_data)
        )

        output = entities_raw | f"Hydrate {entity_class} instances" >> beam.ParDo(
            extractor_utils._ShallowHydrateEntity(
                root_entity_id_field=entity_class.get_class_id_name(),
                entity_class=entity_class,
            ),
        )

        assert_that(
            output,
            equal_to(
                [
                    (
                        supervision_violation.supervision_violation_id,
                        output_violation_entity,
                    )
                ]
            ),
        )

        test_pipeline.run()


class ExtractAssertMatchers:
    """Functions to be used by Apache Beam testing `assert_that` functions to
    validate pipeline outputs."""

    @staticmethod
    def validate_extract_relationship_property_values(
        root_entity_id: int,
        parent_id: int,
        entity_id: int,
    ):
        """Validates that the output of _ExtractAssociationValues
        matches the expected format:

            (root_entity_id, (parent_id, entity_id))

        where the Entity is of the given |class_type|.
        """

        def _validate_extract_relationship_property_entities(output):
            empty = True
            for item in output:
                empty = False
                first_id, other_ids = item
                assert first_id == root_entity_id

                second_id, third_id = other_ids
                assert second_id == parent_id

                assert third_id == entity_id

            assert not empty

        return _validate_extract_relationship_property_entities
