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
"""Tests the pipeline names."""
import unittest
from typing import Dict, Set, Type
from unittest.mock import MagicMock, patch

from recidiviz.big_query.big_query_address import BigQueryAddress
from recidiviz.big_query.big_query_view import BigQueryViewBuilder
from recidiviz.calculator.query.state.dataset_config import (
    NORMALIZED_STATE_DATASET,
    REFERENCE_VIEWS_DATASET,
    STATE_BASE_DATASET,
    STATIC_REFERENCE_TABLES_DATASET,
)
from recidiviz.calculator.query.state.views.reference.us_mo_sentence_statuses import (
    US_MO_SENTENCE_STATUSES_VIEW_BUILDER,
)
from recidiviz.datasets.static_data.config import EXTERNAL_REFERENCE_DATASET
from recidiviz.ingest.direct.dataset_config import (
    raw_latest_views_dataset_for_region,
    raw_tables_dataset_for_region,
)
from recidiviz.ingest.direct.regions.direct_ingest_region_utils import (
    get_existing_direct_ingest_states,
)
from recidiviz.ingest.direct.types.direct_ingest_instance import DirectIngestInstance
from recidiviz.persistence.database.schema.state import schema
from recidiviz.persistence.entity.base_entity import Entity
from recidiviz.persistence.entity.state import entities
from recidiviz.pipelines.ingest.state.pipeline import StateIngestPipeline
from recidiviz.pipelines.metrics.base_metric_pipeline import MetricPipeline
from recidiviz.pipelines.normalization.comprehensive.pipeline import (
    ComprehensiveNormalizationPipeline,
)
from recidiviz.pipelines.supplemental.base_supplemental_dataset_pipeline import (
    SupplementalDatasetPipeline,
)
from recidiviz.pipelines.utils.pipeline_run_utils import (
    collect_all_pipeline_classes,
    collect_all_pipeline_names,
)


def get_all_pipeline_input_view_builders() -> Dict[
    BigQueryAddress, BigQueryViewBuilder
]:
    return {
        builder.address: builder
        for pipeline in collect_all_pipeline_classes()
        for builder in pipeline.all_input_reference_view_builders()
    }


class TestPipelineNames(unittest.TestCase):
    """Tests the names of all pipelines that can be run."""

    def test_all_input_reference_view_builders(self) -> None:
        for pipeline in collect_all_pipeline_classes():
            found_addresses = set()
            for builder in pipeline.all_input_reference_view_builders():
                if builder.address in found_addresses:
                    self.fail(
                        f"Found duplicate builder defined for pipeline "
                        f"[{pipeline.pipeline_name()}]. Within each pipeline, the list "
                        f"returned by all_input_reference_view_builders() should not "
                        f"contain duplicates."
                    )
                found_addresses.add(builder.address)

    def test_collect_all_pipeline_names(self) -> None:
        """Tests that each pipeline has a unique pipeline_name."""
        pipeline_names = collect_all_pipeline_names()

        self.assertCountEqual(set(pipeline_names), pipeline_names)


class TestReferenceViews(unittest.TestCase):
    """Tests reference views are appropriately referenced."""

    def test_all_reference_views_in_dataset(self) -> None:
        """Asserts that all the reference views required by the pipelines are in the
        reference_views dataset."""
        for builder in get_all_pipeline_input_view_builders().values():
            self.assertEqual(
                REFERENCE_VIEWS_DATASET,
                builder.dataset_id,
                f"Found view [{builder.address.to_str()}] that is referenced by "
                f"pipelines but which does not live in the reference_views dataset.",
            )

    @patch(
        "recidiviz.utils.metadata.project_id", MagicMock(return_value="recidiviz-456")
    )
    def test_input_reference_views_have_valid_parents(self) -> None:
        """Require that all view builder queries for view builders referenced by the
        our calc pipelines only query an allowed subset of source tables. We don't want
        our reference queries to be querying other views because those are not updated
        before pipelines run post-deploy.
        """
        all_pipelines_allowed_datasets = {
            *{
                raw_latest_views_dataset_for_region(
                    state_code=state_code, instance=DirectIngestInstance.PRIMARY
                )
                for state_code in get_existing_direct_ingest_states()
            },
            *{
                raw_tables_dataset_for_region(
                    state_code=state_code, instance=DirectIngestInstance.PRIMARY
                )
                for state_code in get_existing_direct_ingest_states()
            },
            EXTERNAL_REFERENCE_DATASET,
            STATIC_REFERENCE_TABLES_DATASET,
        }

        exempted_reference_view_parents = {
            # TODO(#10389): This reference view is used in both normalization and metrics
            #  pipelines. The metrics pipelines should technically only reference
            #  `normalized_state`, but it's not a huge deal that it references `state`
            #  here (legacy sentences aren't normalized) and we'll be deleting this view
            #  once we update all pipelines to use sentences v2 instead.
            US_MO_SENTENCE_STATUSES_VIEW_BUILDER.address: {
                BigQueryAddress(
                    dataset_id=STATE_BASE_DATASET,
                    table_id=schema.StateIncarcerationSentence.__tablename__,
                ),
                BigQueryAddress(
                    dataset_id=STATE_BASE_DATASET,
                    table_id=schema.StateSupervisionSentence.__tablename__,
                ),
            },
        }

        for pipeline in collect_all_pipeline_classes():
            if issubclass(pipeline, ComprehensiveNormalizationPipeline):
                allowed_parent_datasets = {
                    *all_pipelines_allowed_datasets,
                    STATE_BASE_DATASET,
                }
            elif issubclass(pipeline, (MetricPipeline, SupplementalDatasetPipeline)):
                allowed_parent_datasets = {
                    *all_pipelines_allowed_datasets,
                    NORMALIZED_STATE_DATASET,
                }
            elif issubclass(pipeline, StateIngestPipeline):
                allowed_parent_datasets = all_pipelines_allowed_datasets
            else:
                raise ValueError(f"Unexpected pipeline type [{type(pipeline)}]")

            for builder in pipeline.all_input_reference_view_builders():
                parents = builder.build(address_overrides=None).parent_tables
                for parent in parents:
                    if parent.dataset_id in allowed_parent_datasets:
                        continue
                    if (
                        builder.address in exempted_reference_view_parents
                        and parent in exempted_reference_view_parents[builder.address]
                    ):
                        continue

                    raise ValueError(
                        f"Found reference view builder "
                        f"[{builder.address.to_str()}] for pipeline "
                        f"[{pipeline.__name__}] referencing a table in a dataset that "
                        f"is not allowed: {parent.to_str()}."
                    )


class TestPipelineValidations(unittest.TestCase):
    """Tests that specific pipelines are set up correctly."""

    def test_all_pipelines_are_validated(self) -> None:
        pipeline_classes = collect_all_pipeline_classes()

        for pipeline_class in pipeline_classes:
            if issubclass(pipeline_class, SupplementalDatasetPipeline):
                self.assertTrue("SUPPLEMENTAL" in pipeline_class.pipeline_name())
            elif issubclass(pipeline_class, ComprehensiveNormalizationPipeline):
                self.assertTrue("NORMALIZATION" in pipeline_class.pipeline_name())
            elif issubclass(pipeline_class, MetricPipeline):
                default_entities: Set[Type[Entity]] = {
                    entities.StatePerson,
                    entities.StatePersonRace,
                    entities.StatePersonEthnicity,
                }
                self.assertFalse(len(pipeline_class.required_entities()) == 0)
                missing_default_entities = default_entities.difference(
                    set(pipeline_class.required_entities())
                )
                self.assertTrue(len(missing_default_entities) == 0)
