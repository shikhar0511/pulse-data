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
"""Person level demographics - age, race, gender, birthdate"""

from recidiviz.big_query.big_query_view import SimpleBigQueryViewBuilder
from recidiviz.calculator.query.state.dataset_config import (
    NORMALIZED_STATE_DATASET,
    SESSIONS_DATASET,
    STATIC_REFERENCE_TABLES_DATASET,
)
from recidiviz.utils.environment import GCP_PROJECT_STAGING
from recidiviz.utils.metadata import local_project_id_override

PERSON_DEMOGRAPHICS_VIEW_NAME = "person_demographics"

PERSON_DEMOGRAPHICS_VIEW_DESCRIPTION = (
    """Person level demographics - age, race, gender, birthdate"""
)

PERSON_DEMOGRAPHICS_QUERY_TEMPLATE = """
WITH race_or_ethnicity_cte AS  (
    SELECT 
        state_code,
        person_id,
        race as race_or_ethnicity,
    FROM
        `{project_id}.{normalized_state_dataset}.state_person_race`
    UNION ALL
    SELECT 
        state_code,
        person_id,
        -- If a person only has "NOT_HISPANIC" ethnicity and no race then remap to "EXTERNAL_UNKNOWN"
        IF(ethnicity = "NOT_HISPANIC", "EXTERNAL_UNKNOWN", ethnicity) as race_or_ethnicity,
    FROM
        `{project_id}.{normalized_state_dataset}.state_person_ethnicity`
)
    
,  prioritized_race_ethnicity_cte AS (
    SELECT DISTINCT
        state_code,
        person_id,
        FIRST_VALUE(race_or_ethnicity) OVER (
            PARTITION BY state_code, person_id ORDER BY IFNULL(representation_priority, 100)
        ) AS prioritized_race_or_ethnicity,
    FROM
        race_or_ethnicity_cte
    LEFT JOIN
        -- TODO(#19368): Replace this with `external_reference.state_resident_populations`
        `{project_id}.{static_reference_dataset}.state_race_ethnicity_population_counts`
    USING
        (state_code, race_or_ethnicity)
    )

SELECT 
    state_code,
    person_id,
    birthdate,
    COALESCE(gender, "PRESENT_WITHOUT_INFO") AS gender,
    COALESCE(prioritized_race_or_ethnicity, "PRESENT_WITHOUT_INFO") AS prioritized_race_or_ethnicity,
FROM
    `{project_id}.{normalized_state_dataset}.state_person`
FULL OUTER JOIN 
    prioritized_race_ethnicity_cte
USING
    (state_code, person_id) 
ORDER BY
    state_code,
    person_id
"""

PERSON_DEMOGRAPHICS_VIEW_BUILDER = SimpleBigQueryViewBuilder(
    dataset_id=SESSIONS_DATASET,
    view_id=PERSON_DEMOGRAPHICS_VIEW_NAME,
    view_query_template=PERSON_DEMOGRAPHICS_QUERY_TEMPLATE,
    description=PERSON_DEMOGRAPHICS_VIEW_DESCRIPTION,
    normalized_state_dataset=NORMALIZED_STATE_DATASET,
    static_reference_dataset=STATIC_REFERENCE_TABLES_DATASET,
    clustering_fields=["state_code"],
    should_materialize=True,
)

if __name__ == "__main__":
    with local_project_id_override(GCP_PROJECT_STAGING):
        PERSON_DEMOGRAPHICS_VIEW_BUILDER.build_and_print()
