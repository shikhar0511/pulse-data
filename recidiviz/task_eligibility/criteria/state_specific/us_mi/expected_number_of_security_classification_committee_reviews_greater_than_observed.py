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
"""Defines a criteria span view that shows spans of time during which someone is eligible
for a security classification review, as the number of expected reviews is greater than the
number of observed reviews."""

from recidiviz.calculator.query.bq_utils import (
    nonnull_end_date_clause,
    nonnull_end_date_exclusive_clause,
)
from recidiviz.calculator.query.state.dataset_config import (
    ANALYST_VIEWS_DATASET,
    SESSIONS_DATASET,
)
from recidiviz.common.constants.states import StateCode
from recidiviz.task_eligibility.task_criteria_big_query_view_builder import (
    StateSpecificTaskCriteriaBigQueryViewBuilder,
)
from recidiviz.utils.environment import GCP_PROJECT_STAGING
from recidiviz.utils.metadata import local_project_id_override

_CRITERIA_NAME = "US_MI_EXPECTED_NUMBER_OF_SECURITY_CLASSIFICATION_COMMITTEE_REVIEWS_GREATER_THAN_OBSERVED"

_DESCRIPTION = """Defines a criteria span view that shows spans of time during which someone is eligible
for a security classification review. A resident is eligible for: 
    1. An SCC review in the first week they are in solitary confinement 
    2. AN SCC review every 30 days afterwards 
This view keeps a tally of how many SCC reviews a resident should have, and subtracts instances where we 
see an SCC review take place. SCC reviews are summed over the facility/solitary confinement session, so the tally
will restart for each new solitary session at a specific facility. """

_QUERY_TEMPLATE = f"""
   WITH review_dates_preprocessed AS (
       /* This CTE gathers all solitary confinement session start dates, and associates the first scc review. 
       If that review is within 7 days, that date is used to calculate subsequent review due dates, 
       otherwise, 7 days from the solitary start is used. */
        SELECT 
            h.state_code,
            h.person_id,
            h.start_date,
            h.end_date_exclusive,
            COALESCE(s.completion_event_date, DATE_ADD(h.start_date, INTERVAL 7 DAY)) AS first_review_date,
        FROM `{{project_id}}.{{sessions_dataset}}.us_mi_facility_housing_unit_type_collapsed_solitary_sessions` h
        LEFT JOIN `{{project_id}}.{{analyst_views_dataset}}.us_mi_security_classification_committee_review_materialized` s
            ON s.person_id = h.person_id
            AND s.state_code = h.state_code
            --join scc reviews that are done on the start or the end_date_exclusive of a solitary session
            AND s.completion_event_date BETWEEN h.start_date AND {nonnull_end_date_clause('h.end_date_exclusive')}
            AND DATE_DIFF(s.completion_event_date,h.start_date,  DAY) < 7
        WHERE h.housing_unit_type_collapsed_solitary = 'SOLITARY_CONFINEMENT'
            AND h.state_code = 'US_MI'
        --for facility/housing unit sessions where multiple scc reviews happen within the first week
        --take the latest scc review within that time period as the initial review date
        QUALIFY ROW_NUMBER() OVER(PARTITION BY h.person_id, h.start_date ORDER BY s.completion_event_date DESC)=1
    ),
    review_dates AS(
        /* This CTE generates the dates for which an scc review should occur. The first date is the start date of the
        solitary confinement session. The rest of the days are 30 days after the least of the first review 
        and 7 days after the start date, repeating.
         
         Additionally, due to data quality, we only include review dates after the COMS migration (2023-08-14) */
        SELECT 
            state_code,
            person_id, 
            DATE_TRUNC(DATE_ADD(first_review_date, INTERVAL offset DAY), WEEK(MONDAY)) AS change_date
        FROM review_dates_preprocessed p,
            UNNEST(GENERATE_ARRAY(30, 36500, 30)) AS offset
        WHERE
        --calculate recurring scc reviews until the solitary session ends or for 100 years
          offset <= DATE_DIFF({nonnull_end_date_exclusive_clause('end_date_exclusive')}, start_date, DAY)
          AND DATE_ADD(start_date, INTERVAL offset DAY) >= '2023-08-14' 
        UNION ALL
        SELECT 
            state_code,
            person_id, 
            start_date AS change_date,
        FROM review_dates_preprocessed 
        WHERE start_date >= '2023-08-14'
    ),
    population_change_dates AS (
    /* this CTE gathers all dates at which eligibility might change */ 
        
        --add 1 for each expected SCC review (this includes the start dates for solitary sessions that happen 
        --after the COMS migration)  
        SELECT
            state_code,
            person_id,
            change_date,
            1 AS expected_review,
            1 AS activity_type,
        FROM review_dates
        
        UNION ALL   
        
        --include a population change date for solitary sessions that happen before the COMS migration, 
        --so that even though we aren't accruing expected reviews before then, we can still aggregate within sessions. 
        SELECT 
            state_code,
            person_id,
            start_date AS change_date,
            0 AS expected_review,
            0 AS activity_type,
        FROM
            `{{project_id}}.{{sessions_dataset}}.us_mi_facility_housing_unit_type_collapsed_solitary_sessions` h
        WHERE
            state_code = 'US_MI'
            AND housing_unit_type_collapsed_solitary = 'SOLITARY_CONFINEMENT'
            AND start_date <= '2023-08-14'
       
        UNION ALL
        
        -- add a change date for when the solitary session ends
        SELECT 
            state_code,
            person_id,
            h.end_date_exclusive AS change_date,
            0 AS expected_review,
            0 AS activity_type,
        FROM
            `{{project_id}}.{{sessions_dataset}}.us_mi_facility_housing_unit_type_collapsed_solitary_sessions` h
        WHERE
            state_code = 'US_MI'
            AND housing_unit_type_collapsed_solitary = 'SOLITARY_CONFINEMENT'
        
        UNION ALL
        
        --add -1 for every time we observe a review 
        SELECT 
            state_code,
            person_id,
            completion_event_date AS change_date,
            0 AS expected_review,
            -1 AS activity_type,
        FROM
            `{{project_id}}.{{analyst_views_dataset}}.us_mi_security_classification_committee_review_materialized` s
        WHERE completion_event_date >= '2023-08-14'

    ),
    population_change_dates_agg AS (
        SELECT 
            state_code,
            person_id,
            change_date,
            SUM(expected_review) AS expected_review,
            SUM(activity_type) AS activity_type,
        FROM
            population_change_dates
        GROUP BY
            1,2,3
    ),
    time_spans AS (
        SELECT 
            p.state_code,
            p.person_id,
            p.change_date AS start_date,
            LEAD(change_date) OVER (PARTITION BY p.state_code,
                                               p.person_id
                                  ORDER BY change_date) AS end_date,
            p.expected_review, 
            p.activity_type,
        FROM
            population_change_dates_agg p
    ),
    time_spans_agg AS (
        SELECT 
            ts.state_code,
            ts.person_id,
            ts.start_date,
            ts.end_date,
            hu.session_id,
            hu.start_date AS housing_start_date,
            hu.end_date_exclusive AS housing_end_date,
            SUM(expected_review) OVER (PARTITION BY ts.state_code, 
                                                    ts.person_id,
                                                    hu.session_id
                                    ORDER BY ts.start_date
            ) AS expected_reviews,
            SUM(activity_type) OVER (PARTITION BY ts.state_code, 
                                                    ts.person_id,
                                                    hu.session_id
                                    ORDER BY ts.start_date
            ) AS reviews_due,
        FROM
            time_spans ts
        INNER JOIN
            `{{project_id}}.{{sessions_dataset}}.us_mi_facility_housing_unit_type_collapsed_solitary_sessions` hu
            ON ts.person_id = hu.person_id
            AND ts.start_date < {nonnull_end_date_clause('hu.end_date_exclusive')}
            AND hu.start_date < {nonnull_end_date_clause('ts.end_date')}
            AND hu.housing_unit_type_collapsed_solitary = 'SOLITARY_CONFINEMENT'
    )
    SELECT 
        t.state_code,
        t.person_id,
        t.start_date,
        t.end_date,
        t.reviews_due > 0 AS meets_criteria,
        TO_JSON(STRUCT(
                housing_start_date AS facility_solitary_start_date,
                t.expected_reviews AS number_of_expected_reviews,
                t.expected_reviews-t.reviews_due AS number_of_reviews,
                p.change_date AS latest_scc_review_date
            )) AS reason,
    FROM time_spans_agg t
    LEFT JOIN population_change_dates  p
        ON p.state_code = t.state_code
        AND p.person_id = t.person_id 
        AND p.change_date BETWEEN housing_start_date AND {nonnull_end_date_exclusive_clause('housing_end_date')}
        AND p.change_date < {nonnull_end_date_exclusive_clause('t.end_date')}
        --only join SCC reviews
        AND p.activity_type = -1
    --pick latest SCC review within the relevant housing unit session
    QUALIFY ROW_NUMBER() OVER(PARTITION BY t.person_id, t.start_date ORDER BY p.change_date DESC)=1
"""

VIEW_BUILDER: StateSpecificTaskCriteriaBigQueryViewBuilder = (
    StateSpecificTaskCriteriaBigQueryViewBuilder(
        criteria_name=_CRITERIA_NAME,
        description=_DESCRIPTION,
        criteria_spans_query_template=_QUERY_TEMPLATE,
        state_code=StateCode.US_MI,
        sessions_dataset=SESSIONS_DATASET,
        analyst_views_dataset=ANALYST_VIEWS_DATASET,
    )
)

if __name__ == "__main__":
    with local_project_id_override(GCP_PROJECT_STAGING):
        VIEW_BUILDER.build_and_print()
