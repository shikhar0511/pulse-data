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
"""Creates the view builder and view for person/client experiment assignments."""
from recidiviz.big_query.big_query_view import SimpleBigQueryViewBuilder
from recidiviz.calculator.query.experiments.dataset_config import EXPERIMENTS_DATASET
from recidiviz.calculator.query.state.dataset_config import (
    NORMALIZED_STATE_DATASET,
    SESSIONS_DATASET,
    STATIC_REFERENCE_TABLES_DATASET,
)
from recidiviz.common.constants.states import StateCode
from recidiviz.ingest.direct.dataset_config import raw_latest_views_dataset_for_region
from recidiviz.ingest.direct.types.direct_ingest_instance import DirectIngestInstance
from recidiviz.utils.environment import GCP_PROJECT_STAGING
from recidiviz.utils.metadata import local_project_id_override

# date range for covid-era early release policies to take effect
COVID_POLICY_START_DATE = "2020-02-01"
COVID_POLICY_END_DATE = "2021-02-01"

PERSON_ASSIGNMENTS_VIEW_NAME = "person_assignments"

PERSON_ASSIGNMENTS_VIEW_DESCRIPTION = (
    "Tracks assignments of experiment/policy/program variants to persons (clients) in "
    "each experiment."
)

PERSON_ASSIGNMENTS_QUERY_TEMPLATE = """
-- last day data observable in sessions
WITH last_day_of_data AS (
    SELECT
        state_code,
        MIN(last_day_of_data) AS last_day_of_data,
    FROM
        `{project_id}.{sessions_dataset}.compartment_sessions_materialized`
    GROUP BY 1
)

-- Dummy "treatment" to get all persons when first observed in sessions
, first_observed AS (
    SELECT
        "FIRST_OBSERVED" AS experiment_id,
        state_code,
        person_id,
        compartment_level_1 AS variant_id,
        MIN(start_date) AS variant_date,
        NULL AS block_id,
    FROM
        `{project_id}.{sessions_dataset}.compartment_sessions_materialized`
    GROUP BY 1, 2, 3, 4
)

-- Covid-related CPP cohort in ND
, us_nd_community_placement_program AS (
    SELECT 
        "COVID_EARLY_RELEASE" AS experiment_id,
        "US_ND" AS state_code,
        person_id,
        "COMMUNITY_PLACEMENT_PROGRAM" AS variant_id,
        MIN(start_date) AS variant_date,
        NULL AS block_id,
    FROM 
        `{project_id}.{sessions_dataset}.compartment_sessions_materialized` a
    WHERE
        compartment_level_2 = "COMMUNITY_CONFINEMENT"
        AND start_date BETWEEN "{covid_start}" AND "{covid_end}"
    GROUP BY 1, 2, 3, 4
)

-- Covid-related reprieve cohort in PA
, us_pa_covid_reprieves AS (
    SELECT 
        "COVID_EARLY_RELEASE" AS experiment_id,
        "US_PA" AS state_code,
        person_id,
        "TEMPORARY_REPRIEVE" AS variant_id,
        reprieve_date AS variant_date,
        NULL AS block_id,
    FROM 
        `{project_id}.{static_reference_dataset}.us_pa_temporary_reprieves` a
    INNER JOIN
        `{project_id}.{normalized_state_dataset}.state_person_external_id` b
    ON
        a.external_id = b.external_id
        AND b.id_type = "US_PA_INMATE"
    WHERE
        reprieve_date BETWEEN "{covid_start}" AND "{covid_end}"
)

-- Covid-related furlough cohort in PA
, us_pa_covid_furloughs AS (
    SELECT 
        "COVID_EARLY_RELEASE" AS experiment_id,
        "US_PA" AS state_code,
        person_id,
        "FURLOUGH" AS variant_id,
        -- Define first marked movement as treatment
        MIN(DATE(Status_Dt)) AS variant_date,
        NULL AS block_id,
    FROM 
        `{project_id}.{us_pa_raw_data_up_to_date_dataset}.dbo_vwCCISAllMvmt_latest` a
    INNER JOIN (
        SELECT
            CCISMvmt_Id,
        FROM
            `{project_id}.{us_pa_raw_data_up_to_date_dataset}.dbo_vwCCISAllProgDtls_latest`
        WHERE
            -- covid-related furloughs only
            Program_Id = "70"
        )
    USING
        (CCISMvmt_Id)
    INNER JOIN
        `{project_id}.{normalized_state_dataset}.state_person_external_id` b
    ON
        a.Inmate_Number = b.external_id
        AND b.id_type = "US_PA_INMATE"
    WHERE
        DATE(Status_Dt) BETWEEN "{covid_start}" AND "{covid_end}"
    GROUP BY 1, 2, 3, 4
)

-- Union all assignment subqueries
, stacked AS (
    SELECT *
    FROM first_observed
    UNION ALL
    SELECT *
    FROM us_nd_community_placement_program
    UNION ALL
    SELECT *
    FROM us_pa_covid_reprieves
    UNION ALL
    SELECT *
    FROM us_pa_covid_furloughs
)

-- Add state-level last day data observed
SELECT DISTINCT *
FROM stacked
INNER JOIN last_day_of_data USING(state_code)
"""

PERSON_ASSIGNMENTS_VIEW_BUILDER = SimpleBigQueryViewBuilder(
    dataset_id=EXPERIMENTS_DATASET,
    view_id=PERSON_ASSIGNMENTS_VIEW_NAME,
    view_query_template=PERSON_ASSIGNMENTS_QUERY_TEMPLATE,
    description=PERSON_ASSIGNMENTS_VIEW_DESCRIPTION,
    sessions_dataset=SESSIONS_DATASET,
    normalized_state_dataset=NORMALIZED_STATE_DATASET,
    static_reference_dataset=STATIC_REFERENCE_TABLES_DATASET,
    us_pa_raw_data_up_to_date_dataset=raw_latest_views_dataset_for_region(
        state_code=StateCode.US_PA, instance=DirectIngestInstance.PRIMARY
    ),
    covid_start=COVID_POLICY_START_DATE,
    covid_end=COVID_POLICY_END_DATE,
    should_materialize=True,
    clustering_fields=["experiment_id"],
)

if __name__ == "__main__":
    with local_project_id_override(GCP_PROJECT_STAGING):
        PERSON_ASSIGNMENTS_VIEW_BUILDER.build_and_print()
