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
"""Identifies eligibility spans at the person-sentence level for earned discharge in OR"""

from recidiviz.big_query.big_query_view import SimpleBigQueryViewBuilder
from recidiviz.calculator.query.sessions_query_fragments import (
    aggregate_adjacent_spans,
    create_sub_sessions_with_attributes,
)
from recidiviz.calculator.query.state.dataset_config import ANALYST_VIEWS_DATASET
from recidiviz.utils.environment import GCP_PROJECT_STAGING
from recidiviz.utils.metadata import local_project_id_override

US_OR_EARNED_DISCHARGE_SENTENCE_ELIGIBILITY_SPANS_VIEW_NAME = (
    "us_or_earned_discharge_sentence_eligibility_spans"
)

US_OR_EARNED_DISCHARGE_SENTENCE_ELIGIBILITY_SPANS_VIEW_DESCRIPTION = """Identifies eligibility spans at the person-sentence level for earned discharge in OR"""

US_OR_EARNED_DISCHARGE_SENTENCE_ELIGIBILITY_SPANS_QUERY_TEMPLATE = f"""
    WITH sentence_subcriteria_eligibility_spans AS (
        SELECT * EXCEPT(meets_criteria),
            meets_criteria AS sentence_date,
            NULL AS served_6_months,
            NULL AS served_half_of_sentence,
            NULL AS statute,
            NULL AS no_convictions_since_sentence_start_date,
        FROM `{{project_id}}.{{analyst_dataset}}.us_or_sentence_imposition_date_eligible`
        UNION ALL
        SELECT * EXCEPT(meets_criteria),
            NULL AS sentence_date,
            meets_criteria AS served_6_months,
            NULL AS served_half_of_sentence,
            NULL AS statute,
            NULL AS no_convictions_since_sentence_start_date,
        FROM `{{project_id}}.{{analyst_dataset}}.us_or_served_6_months_supervision`
        UNION ALL
        SELECT * EXCEPT(meets_criteria),
            NULL AS sentence_date,
            NULL AS served_6_months,
            meets_criteria AS served_half_of_sentence,
            NULL AS statute,
            NULL AS no_convictions_since_sentence_start_date,
        FROM `{{project_id}}.{{analyst_dataset}}.us_or_served_half_sentence`
        UNION ALL
        SELECT * EXCEPT(meets_criteria),
            NULL AS sentence_date,
            NULL AS served_6_months,
            NULL AS served_half_of_sentence,
            meets_criteria AS statute,
            NULL AS no_convictions_since_sentence_start_date,
        FROM `{{project_id}}.{{analyst_dataset}}.us_or_statute_eligible`
        UNION ALL
        SELECT * EXCEPT(meets_criteria),
            NULL AS sentence_date,
            NULL AS served_6_months,
            NULL AS served_half_of_sentence,
            NULL AS statute,
            meets_criteria AS no_convictions_since_sentence_start_date,
        FROM `{{project_id}}.{{analyst_dataset}}.us_or_no_convictions_since_sentence_start`
    ),
    {create_sub_sessions_with_attributes("sentence_subcriteria_eligibility_spans", index_columns=["state_code", "person_id", "sentence_id"])},
    sub_sessions_with_attributes_condensed AS (
        SELECT
            state_code,
            person_id,
            sentence_id,
            start_date,
            end_date,
            /* Note: using COALESCE(LOGICAL_AND(), FALSE) prevents the problem of ending
            up with NULL for the meets_criteria_ fields, which can happen if there is no
            row in the relevant view for that person-sentence span (i.e., there's
            nothing going into the LOGICAL_AND). By using COALESCE here, we ensure that
            each of these criteria is always either TRUE or FALSE (and never NULL). */
            COALESCE(LOGICAL_AND(sentence_date), FALSE) AS meets_criteria_sentence_date,
            COALESCE(LOGICAL_AND(served_6_months), FALSE) AS meets_criteria_served_6_months,
            COALESCE(LOGICAL_AND(served_half_of_sentence), FALSE) AS meets_criteria_served_half_of_sentence,
            COALESCE(LOGICAL_AND(statute), FALSE) AS meets_criteria_statute,
            COALESCE(LOGICAL_AND(no_convictions_since_sentence_start_date), FALSE) AS meets_criteria_no_convictions_since_sentence_start_date,
        FROM sub_sessions_with_attributes
        GROUP BY 1, 2, 3, 4, 5
    ),
    sentence_eligibility_spans AS (
        SELECT
            state_code,
            person_id,
            sentence_id,
            start_date,
            end_date,
            (meets_criteria_sentence_date
                AND meets_criteria_served_6_months
                AND meets_criteria_served_half_of_sentence
                AND meets_criteria_statute
                AND meets_criteria_no_convictions_since_sentence_start_date
            ) AS is_eligible,
            meets_criteria_sentence_date,
            meets_criteria_served_6_months,
            meets_criteria_served_half_of_sentence,
            meets_criteria_statute,
            meets_criteria_no_convictions_since_sentence_start_date,
        FROM sub_sessions_with_attributes_condensed
    ),
    sentence_eligibility_spans_aggregated AS (
        {aggregate_adjacent_spans("sentence_eligibility_spans",
                                  index_columns=['state_code', 'person_id', 'sentence_id'],
                                  attribute=['is_eligible', 'meets_criteria_sentence_date', 'meets_criteria_served_6_months', 'meets_criteria_served_half_of_sentence', 'meets_criteria_statute', 'meets_criteria_no_convictions_since_sentence_start_date'])}
    )
    SELECT
        * EXCEPT (session_id, date_gap_id)
    FROM sentence_eligibility_spans_aggregated
"""

US_OR_EARNED_DISCHARGE_SENTENCE_ELIGIBILITY_SPANS_VIEW_BUILDER = SimpleBigQueryViewBuilder(
    dataset_id=ANALYST_VIEWS_DATASET,
    view_id=US_OR_EARNED_DISCHARGE_SENTENCE_ELIGIBILITY_SPANS_VIEW_NAME,
    description=US_OR_EARNED_DISCHARGE_SENTENCE_ELIGIBILITY_SPANS_VIEW_DESCRIPTION,
    view_query_template=US_OR_EARNED_DISCHARGE_SENTENCE_ELIGIBILITY_SPANS_QUERY_TEMPLATE,
    analyst_dataset=ANALYST_VIEWS_DATASET,
    should_materialize=True,
)

if __name__ == "__main__":
    with local_project_id_override(GCP_PROJECT_STAGING):
        US_OR_EARNED_DISCHARGE_SENTENCE_ELIGIBILITY_SPANS_VIEW_BUILDER.build_and_print()
