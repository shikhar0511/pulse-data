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
"""The population spans metric calculation pipeline. See recidiviz/tools/calculator/run_sandbox_calculation_pipeline.py
for details on how to launch a local run."""

from __future__ import absolute_import

from typing import Dict, List, Type, Union

from recidiviz.big_query.big_query_view import BigQueryViewBuilder
from recidiviz.common.constants.states import StateCode
from recidiviz.persistence.entity.base_entity import Entity
from recidiviz.persistence.entity.state import entities, normalized_entities
from recidiviz.persistence.entity.state.normalized_state_entity import (
    NormalizedStateEntity,
)
from recidiviz.pipelines.metrics.base_identifier import BaseIdentifier
from recidiviz.pipelines.metrics.base_metric_pipeline import MetricPipeline
from recidiviz.pipelines.metrics.base_metric_producer import BaseMetricProducer
from recidiviz.pipelines.metrics.population_spans import identifier, metric_producer
from recidiviz.pipelines.utils.state_utils.state_specific_delegate import (
    StateSpecificDelegate,
)
from recidiviz.pipelines.utils.state_utils.state_specific_incarceration_delegate import (
    StateSpecificIncarcerationDelegate,
)
from recidiviz.pipelines.utils.state_utils.state_specific_supervision_delegate import (
    StateSpecificSupervisionDelegate,
)


class PopulationSpanMetricsPipeline(MetricPipeline):
    """Defines the population span metric calculation pipeline."""

    @classmethod
    def required_entities(
        cls,
    ) -> List[Union[Type[Entity], Type[NormalizedStateEntity]]]:
        return [
            entities.StatePerson,
            entities.StatePersonRace,
            entities.StatePersonEthnicity,
            entities.StatePersonExternalId,
            normalized_entities.NormalizedStateIncarcerationPeriod,
            normalized_entities.NormalizedStateSupervisionPeriod,
            normalized_entities.NormalizedStateSupervisionCaseTypeEntry,
        ]

    @classmethod
    def input_reference_view_builders(cls) -> List[BigQueryViewBuilder]:
        return []

    @classmethod
    def state_specific_required_delegates(cls) -> List[Type[StateSpecificDelegate]]:
        return [
            StateSpecificIncarcerationDelegate,
            StateSpecificSupervisionDelegate,
        ]

    @classmethod
    def state_specific_input_reference_view_builders(
        cls,
    ) -> Dict[StateCode, List[BigQueryViewBuilder]]:
        return {}

    @classmethod
    def pipeline_name(cls) -> str:
        return "POPULATION_SPAN_METRICS"

    @classmethod
    def identifier(cls) -> BaseIdentifier:
        return identifier.PopulationSpanIdentifier()

    @classmethod
    def metric_producer(cls) -> BaseMetricProducer:
        return metric_producer.PopulationSpanMetricProducer()

    @classmethod
    def include_calculation_limit_args(cls) -> bool:
        return False
