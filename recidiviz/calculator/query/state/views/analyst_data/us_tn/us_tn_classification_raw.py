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
"""Computes custody levels from raw TN data"""

from recidiviz.big_query.big_query_view import SimpleBigQueryViewBuilder
from recidiviz.calculator.query.state.dataset_config import ANALYST_VIEWS_DATASET
from recidiviz.utils.environment import GCP_PROJECT_STAGING
from recidiviz.utils.metadata import local_project_id_override

US_TN_CLASSIFICATION_RAW_VIEW_NAME = "us_tn_classification_raw"

US_TN_CLASSIFICATION_RAW_VIEW_DESCRIPTION = (
    """Computes custody levels from raw TN data"""
)

US_TN_CLASSIFICATION_RAW_QUERY_TEMPLATE = """
    -- TODO(#5178): Once custody level ingest issues in TN are resolved, this view can be deleted
    SELECT
        state_code,
        person_id,
        custody_level,
        custody_level_raw_text,
        classification_date AS start_date,
        LEAD(classification_date) OVER (PARTITION BY person_id ORDER BY classification_date ASC) AS end_date_exclusive, 
    FROM (
        SELECT
            state_code,
            person_id,
            CAST(CAST(ClassificationDate AS DATETIME) AS DATE) AS classification_date,
            RecommendedCustody AS custody_level_raw_text,
            CASE 
                WHEN RecommendedCustody = "MAX" THEN "MAXIMUM"
                WHEN RecommendedCustody = "CLS" THEN "CLOSE"
                WHEN RecommendedCustody = "MED" THEN "MEDIUM"
                WHEN RecommendedCustody LIKE "MI%" THEN "MINIMUM"
            END AS custody_level
        FROM `{project_id}.us_tn_raw_data_up_to_date_views.Classification_latest` c
        INNER JOIN `{project_id}.normalized_state.state_person_external_id` pei
            ON c.OffenderID = pei.external_id
            AND pei.state_code = "US_TN"
        -- Only keep classifications that were approved
        WHERE ClassificationDecision = 'A'
        -- Most classifications should be unique on person-date. When they're not, we keep the latest decision date
        QUALIFY ROW_NUMBER() OVER(
            PARTITION BY OffenderID,
            CAST(ClassificationDate AS DATETIME)
            ORDER BY CAST(ClassificationDecisionDate AS DATETIME) DESC
        ) = 1    
    )
        
"""

US_TN_CLASSIFICATION_RAW_VIEW_BUILDER = SimpleBigQueryViewBuilder(
    dataset_id=ANALYST_VIEWS_DATASET,
    view_id=US_TN_CLASSIFICATION_RAW_VIEW_NAME,
    description=US_TN_CLASSIFICATION_RAW_VIEW_DESCRIPTION,
    view_query_template=US_TN_CLASSIFICATION_RAW_QUERY_TEMPLATE,
    should_materialize=True,
)

if __name__ == "__main__":
    with local_project_id_override(GCP_PROJECT_STAGING):
        US_TN_CLASSIFICATION_RAW_VIEW_BUILDER.build_and_print()
