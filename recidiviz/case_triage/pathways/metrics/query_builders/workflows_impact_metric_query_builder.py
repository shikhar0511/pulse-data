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
""" MetricQueryBuilder for workflows impact metrics """

import attr
from sqlalchemy.orm import Query

from recidiviz.case_triage.pathways.metrics.query_builders.metric_query_builder import (
    FetchMetricParams,
    MetricQueryBuilder,
)


@attr.s(auto_attribs=True)
class WorkflowsImpactMetricQueryBuilder(MetricQueryBuilder):
    """Builder for Pathways postgres queries that return workflows impact data matching a filter"""

    def __attrs_post_init__(self) -> None:
        super().__attrs_post_init__()

        required_attributes = [
            "state_code",
            "supervision_district",
            "district_name",
            "variant_id",
            "variant_date",
            "start_date",
            "end_date",
            "months_since_treatment",
            "avg_daily_population",
            "avg_population_limited_supervision_level",
        ]

        self.base_columns = [
            getattr(self.model, attribute)
            for attribute in required_attributes
            if hasattr(self.model, attribute)
        ]

        if len(self.base_columns) != len(required_attributes):
            raise ValueError(
                "WorkflowsImpactMetricQueryBuilder model must have required attributes"
            )

    def build_query(self, params: FetchMetricParams) -> Query:
        return (
            Query([*self.base_columns])
            .filter(*self.build_filter_conditions(params))
            .order_by(*self.base_columns)
        )
