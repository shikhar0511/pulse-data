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

"""Defines a criteria view that shows spans of time for which residents have
registration requirements (sexual offender, violent offender, etc.)
"""
from recidiviz.calculator.query.sessions_query_fragments import (
    create_sub_sessions_with_attributes,
)
from recidiviz.calculator.query.state.dataset_config import NORMALIZED_STATE_DATASET
from recidiviz.common.constants.states import StateCode
from recidiviz.ingest.direct.dataset_config import raw_latest_views_dataset_for_region
from recidiviz.ingest.direct.types.direct_ingest_instance import DirectIngestInstance
from recidiviz.task_eligibility.task_criteria_big_query_view_builder import (
    StateSpecificTaskCriteriaBigQueryViewBuilder,
)
from recidiviz.utils.environment import GCP_PROJECT_STAGING
from recidiviz.utils.metadata import local_project_id_override

_CRITERIA_NAME = "US_ND_HAS_REGISTRATION_REQUIREMENTS"

_DESCRIPTION = """Defines a criteria view that shows spans of time for which residents have
registration requirements (sexual offender, violent offender, etc.)
"""

_QUERY_TEMPLATE = f"""
WITH registration_requirements AS (
    # Folks who have registration requirements
    SELECT 
    peid.state_code,
    peid.person_id,
    SAFE_CAST(PARSE_TIMESTAMP('%m/%d/%Y %I:%M:%S%p', ot.OFFENSEDATE) AS DATE) AS start_date,
    SAFE_CAST(PARSE_TIMESTAMP('%m/%d/%Y %I:%M:%S%p', ot.INACTIVEDATE) AS DATE) AS end_date,
    SAFE_CAST(PARSE_TIMESTAMP('%m/%d/%Y %I:%M:%S%p', ot.OFFENSEDATE) AS DATE) AS offense_date,
    FROM `{{project_id}}.{{raw_data_up_to_date_views_dataset}}.docstars_offensestable_latest` ot
    LEFT JOIN `{{project_id}}.{{normalized_state_dataset}}.state_person_external_id` peid
    ON ot.SID = peid.external_id
        AND peid.state_code = 'US_ND'
        AND id_type = 'US_ND_SID'
    WHERE REQUIRES_REGISTRATION = 'Y'
),
{create_sub_sessions_with_attributes(table_name='registration_requirements')}
SELECT 
    state_code,
    person_id,
    start_date,
    end_date,
    TRUE AS meets_criteria,
    TO_JSON(STRUCT(
        MAX(offense_date) AS latest_offense_requiring_registration
    )) AS reason,
FROM sub_sessions_with_attributes
GROUP BY 1,2,3,4,5
"""

VIEW_BUILDER: StateSpecificTaskCriteriaBigQueryViewBuilder = (
    StateSpecificTaskCriteriaBigQueryViewBuilder(
        criteria_name=_CRITERIA_NAME,
        description=_DESCRIPTION,
        state_code=StateCode.US_ND,
        criteria_spans_query_template=_QUERY_TEMPLATE,
        raw_data_up_to_date_views_dataset=raw_latest_views_dataset_for_region(
            state_code=StateCode.US_ND, instance=DirectIngestInstance.PRIMARY
        ),
        normalized_state_dataset=NORMALIZED_STATE_DATASET,
        meets_criteria_default=False,
    )
)

if __name__ == "__main__":
    with local_project_id_override(GCP_PROJECT_STAGING):
        VIEW_BUILDER.build_and_print()
