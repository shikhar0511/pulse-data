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
"""Queries information needed to fill out reclassification form in ME
"""
from recidiviz.big_query.big_query_view import SimpleBigQueryViewBuilder
from recidiviz.calculator.query.bq_utils import nonnull_end_date_clause
from recidiviz.calculator.query.state import dataset_config
from recidiviz.calculator.query.state.dataset_config import (
    NORMALIZED_STATE_DATASET,
    SESSIONS_DATASET,
)
from recidiviz.calculator.query.state.views.workflows.firestore.opportunity_record_query_fragments import (
    join_current_task_eligibility_spans_with_external_id,
)
from recidiviz.common.constants.states import StateCode
from recidiviz.ingest.direct.dataset_config import raw_latest_views_dataset_for_region
from recidiviz.ingest.direct.types.direct_ingest_instance import DirectIngestInstance
from recidiviz.task_eligibility.dataset_config import (
    completion_event_state_specific_dataset,
    task_eligibility_spans_state_specific_dataset,
)
from recidiviz.task_eligibility.utils.almost_eligible_query_fragments import (
    clients_eligible,
    json_to_array_cte,
    x_time_away_from_eligibility,
)
from recidiviz.task_eligibility.utils.us_me_query_fragments import (
    case_plan_goals_helper,
    disciplinary_reports_helper,
    program_enrollment_helper,
)
from recidiviz.utils.environment import GCP_PROJECT_STAGING
from recidiviz.utils.metadata import local_project_id_override

US_ME_RECLASSIFICATION_REVIEW_FORM_RECORD_VIEW_NAME = (
    "us_me_custody_reclassification_review_form_record"
)

US_ME_RECLASSIFICATION_REVIEW_FORM_RECORD_DESCRIPTION = """
    Queries information needed to fill out reclassification form in ME
    """

US_ME_RECLASSIFICATION_REVIEW_FORM_RECORD_QUERY_TEMPLATE = f"""
WITH current_incarceration_pop_cte AS (
{join_current_task_eligibility_spans_with_external_id(
    state_code= "'US_ME'", 
    tes_task_query_view = 'custody_reclassification_review_form_materialized',
    id_type = "'US_ME_DOC'")}
),
# Arrival at the Current Facility
arrival_date_cte AS (
    SELECT
     person_id,
     state_code,
     CAST(start_date AS STRING) AS form_information_arrival_date,
    FROM
      `{{project_id}}.{{sessions_dataset}}.location_sessions_materialized`
    WHERE state_code = 'US_ME'
    AND CURRENT_DATE('US/Pacific') BETWEEN start_date AND {nonnull_end_date_clause('end_date_exclusive')}
    AND facility is not null
    ORDER BY person_id, start_date
),
# TODO(#26591): Refactor functions to be state agnostic and use query fragments
# Grabs the current offense(s) for a client, separated by @@@
current_offense_cte AS (
    WITH
      sent_preprocessed AS (
      SELECT
        sent.state_code,
        sent.person_id,
        sent.sentences_preprocessed_id,
        sc.description,
      FROM
        `{{project_id}}.{{sessions_dataset}}.sentences_preprocessed_materialized` sent
      LEFT JOIN
        `{{project_id}}.{{normalized_state_dataset}}.state_charge_incarceration_sentence_association` chip
      ON
        chip.incarceration_sentence_id = sent.sentence_id
      LEFT JOIN
        `{{project_id}}.{{normalized_state_dataset}}.state_charge` sc
      ON
        sc.charge_id = chip.charge_id
      WHERE
        sent.sentence_type = 'INCARCERATION'
        AND sent.state_code = 'US_ME' 
        order by person_id)
    SELECT
      span.state_code,
      span.person_id,
      STRING_AGG(sent.description, " @@@ ") AS form_information_current_offenses,
    FROM
      `{{project_id}}.{{sessions_dataset}}.sentence_spans_materialized` span,
      UNNEST (sentences_preprocessed_id_array_projected_completion) AS sentences_preprocessed_id
    INNER JOIN
      sent_preprocessed sent
    USING
      (state_code,
        person_id,
        sentences_preprocessed_id)
    WHERE
      span.state_code = 'US_ME'
      AND CURRENT_DATE('US/Eastern') BETWEEN span.start_date
      AND IFNULL(span.end_date, '9999-12-31')
    GROUP BY
      1,
      2
),
# Grabs a list of work assignments for a client, separated by @@@
work_assignments_cte AS (
    WITH
      cte AS (
      SELECT
        person_id,
        SAFE_CAST(LEFT(ci.START_DATE, 10) AS STRING) AS work_assignments_start_date,
        SAFE_CAST(LEFT(ci.END_DATE, 10) AS STRING) AS work_assignments_end_date,
        IFNULL(EMPLOYER_TX, 'Employer Unknown') AS employer,
        IFNULL(OCCUPATION_TX, 'Occupation Unknown') AS occupation,
      FROM
        `{{project_id}}.{{us_me_raw_data_up_to_date_dataset}}.CIS_128_EMPLOYMENT_HISTORY_latest` ci
      INNER JOIN
        `{{project_id}}.{{normalized_state_dataset}}.state_person_external_id` ei
      ON
        ci.Cis_100_Client_Id = external_id
        AND id_type = 'US_ME_DOC'
        AND SAFE_CAST(LEFT(ci.START_DATE, 10) AS DATE) <= CURRENT_DATE('US/Pacific')
        AND DATE_SUB(CURRENT_DATE('US/Pacific'), INTERVAL 6 MONTH) < IFNULL(SAFE_CAST(LEFT(ci.END_DATE, 10) AS DATE), '9999-12-31')
        AND CURRENT_DATE >= IFNULL(SAFE_CAST(LEFT(ci.START_DATE, 10) AS DATE), '1000-01-01')
      ORDER BY
        2 DESC)
    SELECT
      "US_ME" AS state_code,
      person_id,
      STRING_AGG(CONCAT(employer, ', ', 
                        occupation, '; ', 
                        work_assignments_start_date, ': ', 
                        IFNULL(work_assignments_end_date, 'Present')), ' @@@ ') AS form_information_work_assignments
    FROM
      cte
    GROUP BY
      1,
      2
),
# Grabs the program assignments for each client, separated by @@@
program_assignments_cte AS (
    WITH
      cte AS (
        SELECT
          mp.CIS_100_CLIENT_ID AS external_id,
          CONCAT(st.E_STAT_TYPE_DESC,' - ', pr.NAME_TX, ' - ', ps.Comments_Tx, ' - ', CAST(SAFE_CAST(LEFT(mp.MODIFIED_ON_DATE, 10) AS DATE) AS STRING)) AS form_information_program_enrollment,
        FROM {program_enrollment_helper()}
        WHERE
          pr.NAME_TX IS NOT NULL QUALIFY ROW_NUMBER() OVER(PARTITION BY mp.ENROLL_ID ORDER BY Effct_Datetime DESC) = 1
        ORDER BY
          (SAFE_CAST(LEFT(mp.MODIFIED_ON_DATE, 10) AS DATE)) DESC)
    SELECT
      person_id,
      state_code,
      STRING_AGG(form_information_program_enrollment, ' @@@ ') AS form_information_program_enrollment
    FROM
      cte
    INNER JOIN
      `{{project_id}}.{{normalized_state_dataset}}.state_person_external_id` pei
    USING
      (external_id)
    WHERE
      pei.id_type = 'US_ME_DOC'
    GROUP BY
      1,2
),
# Grabs the case plan goals for each client, separated by @@@
case_plan_goals_cte AS (
    WITH
      cte AS (
      SELECT
        Cis_200_Cis_100_Client_Id AS external_id,
        CONCAT(Domain_Goal_Desc,' - ', Goal_Status_Desc, ' - ',
        IF
          (E_Goal_Type_Desc = 'Other', CONCAT(E_Goal_Type_Desc, " - ",Other), E_Goal_Type_Desc)) AS form_information_case_plan_goals,
        DATE(SAFE.PARSE_DATETIME("%m/%d/%Y %I:%M:%S %p", Open_Date)) AS event_date,
      FROM (
        SELECT
          *
        FROM {case_plan_goals_helper()}))
      SELECT
      person_id,
      state_code,
      STRING_AGG(form_information_case_plan_goals, ' @@@ ') AS form_information_case_plan_goals
    FROM
      cte
    INNER JOIN
      `{{project_id}}.{{normalized_state_dataset}}.state_person_external_id` pei
    USING
      (external_id)
    WHERE
      pei.id_type = 'US_ME_DOC'
    GROUP BY
      1,2
),
# Grabs the furlough dates for each client, separated by @@@
furloughs_cte AS (
    SELECT
      state_code,
      person_id,
      STRING_AGG(CAST(completion_event_date AS STRING), ", ") as form_information_furloughs,
    FROM (
      SELECT
        *
      FROM
        `{{project_id}}.{{task_eligibility_completion_events_dataset}}.granted_furlough_materialized`
      ORDER BY
        completion_event_date DESC )
    WHERE
      state_code = 'US_ME'
      AND DATE_SUB(CURRENT_DATE, INTERVAL 6 MONTH) <= completion_event_date
    GROUP BY
      1,2
),
# Grabs information on disciplinary reports for each client, separated by @@@
disciplinary_reports_cte AS (
    WITH
      cte AS (
      SELECT
        "US_ME" AS state_code,
        ei.person_id,
        CONCAT(
        IF
          (vd.Cis_1813_Disposition_Outcome_Type_Cd IS NULL, 
          CONCAT('Pending since ', SAFE_CAST(LEFT(dc.CREATED_ON_DATE, 10) AS STRING)), 
          vdt.E_Violation_Disposition_Type_Desc), ' - ', 
          SAFE_CAST(LEFT(dc.HEARING_ACTUALLY_HELD_DATE, 10) AS DATE)) AS form_information_disciplinary_reports,
      FROM {disciplinary_reports_helper()}
      WHERE
        # Drop if logical delete = yes
        COALESCE(dc.LOGICAL_DELETE_IND, 'N') != 'Y'
        AND COALESCE(vd.Logical_Delete_Ind, 'N') != 'Y'
        # Whenever a disciplinary sanction has informal sanctions taken, it does not affect eligibility.
        AND COALESCE(dc.DISCIPLINARY_ACTION_FORMAL_IND, 'Y') != 'N'
        AND DATE_SUB(CURRENT_DATE, INTERVAL 6 MONTH) <= SAFE_CAST(LEFT(dc.HEARING_ACTUALLY_HELD_DATE, 10) AS DATE)
      ORDER BY
        SAFE_CAST(LEFT(dc.HEARING_ACTUALLY_HELD_DATE, 10) AS DATE) DESC)
    SELECT
      state_code,
      person_id,
      STRING_AGG(form_information_disciplinary_reports, " @@@ ") as form_information_disciplinary_reports,
    FROM
      cte
    GROUP BY 1, 2
),
escape_history_cte AS (
    -- Escape sentences history in the past 10 years
    SELECT 
        state_code,
        person_id,
        STRING_AGG(CONCAT(
            CAST(date_imposed AS STRING),
            ' - ',
            description
        ), '@@@') form_information_escape_history_10_years
    FROM `{{project_id}}.{{sessions_dataset}}.sentences_preprocessed_materialized` 
    WHERE statute IS NOT NULL
        -- Escape statutes
        AND statute IN ('B_17-A_756', 'C_17-A_755', 'D_17-A_755', 'B_17-A_755', 'C_17-A_756')
        AND date_imposed > DATE_SUB(CURRENT_DATE('US/Eastern'), INTERVAL 10 YEAR)
        AND state_code = 'US_ME'
    GROUP BY 1,2
),
probation_term_cte AS (
  -- Probation sentences that are pending and that follow the incarceration sentence
  SELECT 
      state_code,
      person_id,
      'YES' AS form_information_sentence_includes_probation
  FROM `{{project_id}}.{{normalized_state_dataset}}.state_supervision_sentence`
  WHERE state_code = 'US_ME'
      AND supervision_type = 'PROBATION'
      AND effective_date > CURRENT_DATE('US/Eastern')
      AND status = 'PENDING'
  GROUP BY 1,2
),
json_to_array_cte AS (
        {json_to_array_cte('current_incarceration_pop_cte')}
    ),
eligible_and_almost_eligible_clients AS (

    -- ELIGIBLE
    {clients_eligible(from_cte = 'current_incarceration_pop_cte')}
    
    UNION ALL
    
    -- Almost Eligible - 1 month away from reclassification reset date
        -- Function uses strictly less than and we want 1 months inclusive so time_interval=2
        {x_time_away_from_eligibility(
            time_interval= 2,
            date_part= 'MONTH',
            criteria_name= 'US_ME_INCARCERATION_PAST_RELEVANT_CLASSIFICATION_DATE',
            from_cte_table_name = "json_to_array_cte",
        )}

)
SELECT
  *
FROM
  eligible_and_almost_eligible_clients
LEFT JOIN
  arrival_date_cte
USING
  (person_id, state_code)
LEFT JOIN
  current_offense_cte
USING
  (person_id, state_code)
LEFT JOIN
  work_assignments_cte
USING
  (person_id, state_code)
LEFT JOIN
  program_assignments_cte
USING
  (person_id, state_code)
LEFT JOIN
  case_plan_goals_cte
USING
  (person_id, state_code)
LEFT JOIN
  furloughs_cte
USING
  (person_id, state_code)
LEFT JOIN
  disciplinary_reports_cte
USING
  (person_id, state_code)
LEFT JOIN
  escape_history_cte
USING
  (person_id, state_code)
LEFT JOIN
  probation_term_cte ptc
USING
  (person_id, state_code)
"""

US_ME_RECLASSIFICATION_REVIEW_FORM_RECORD_VIEW_BUILDER = SimpleBigQueryViewBuilder(
    dataset_id=dataset_config.WORKFLOWS_VIEWS_DATASET,
    view_id=US_ME_RECLASSIFICATION_REVIEW_FORM_RECORD_VIEW_NAME,
    view_query_template=US_ME_RECLASSIFICATION_REVIEW_FORM_RECORD_QUERY_TEMPLATE,
    description=US_ME_RECLASSIFICATION_REVIEW_FORM_RECORD_DESCRIPTION,
    normalized_state_dataset=NORMALIZED_STATE_DATASET,
    sessions_dataset=SESSIONS_DATASET,
    task_eligibility_dataset=task_eligibility_spans_state_specific_dataset(
        StateCode.US_ME
    ),
    task_eligibility_completion_events_dataset=completion_event_state_specific_dataset(
        StateCode.US_ME
    ),
    us_me_raw_data_up_to_date_dataset=raw_latest_views_dataset_for_region(
        state_code=StateCode.US_ME, instance=DirectIngestInstance.PRIMARY
    ),
    should_materialize=True,
)

if __name__ == "__main__":
    with local_project_id_override(GCP_PROJECT_STAGING):
        US_ME_RECLASSIFICATION_REVIEW_FORM_RECORD_VIEW_BUILDER.build_and_print()
