# Recidiviz - a data platform for criminal justice reform
# Copyright (C) 2024 Recidiviz, Inc.
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
"""Information about PagerDuty services."""

import attr

from recidiviz.common import attr_validators
from recidiviz.common.constants.states import StateCode


@attr.define
class RecidivizPagerDutyService:
    """Structure holding information about a service managed by the Recidiviz repo.
    For the full list of services, see
    https://recidiviz.pagerduty.com/service-directory.
    """

    project_id: str = attr.ib(validator=attr_validators.is_str)
    service_integration_email: str = attr.ib(validator=attr_validators.is_str)

    @classmethod
    def data_platform_airflow_service(
        cls, project_id: str
    ) -> "RecidivizPagerDutyService":
        """Returns the service for alerts related to state-agnostic Airflow data
        platform task failures.
        """
        return RecidivizPagerDutyService(
            project_id=project_id,
            service_integration_email=cls._build_integration_email(
                "data-platform-airflow", project_id=project_id
            ),
        )

    @classmethod
    def monitoring_airflow_service(cls, project_id: str) -> "RecidivizPagerDutyService":
        """Returns the service for alerts related to Airflow monitoring infrastructure
        failures.
        """
        return RecidivizPagerDutyService(
            project_id=project_id,
            service_integration_email=cls._build_integration_email(
                "monitoring-airflow", project_id=project_id
            ),
        )

    @classmethod
    def airflow_service_for_state_code(
        cls, project_id: str, state_code: StateCode
    ) -> "RecidivizPagerDutyService":
        """Returns the service for alerts related to state-specific Airflow data
        platform task failures for the given state_code.
        """
        state_code_str = state_code.value.lower().replace("_", "-")
        base_username = f"{state_code_str}-airflow"
        return RecidivizPagerDutyService(
            project_id=project_id,
            service_integration_email=cls._build_integration_email(
                base_username, project_id=project_id
            ),
        )

    @staticmethod
    def _build_integration_email(base_username: str, project_id: str) -> str:
        return f"{base_username}-{project_id}@recidiviz.pagerduty.com"
