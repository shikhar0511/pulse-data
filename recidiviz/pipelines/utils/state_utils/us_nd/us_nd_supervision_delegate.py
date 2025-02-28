# Recidiviz - a data platform for criminal justice reform
# Copyright (C) 2021 Recidiviz, Inc.
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
"""US_ND implementation of the supervision delegate"""
from typing import List, Optional

from recidiviz.common.constants.state.state_assessment import (
    StateAssessmentClass,
    StateAssessmentType,
)
from recidiviz.common.constants.state.state_incarceration_period import (
    StateIncarcerationPeriodReleaseReason,
)
from recidiviz.common.constants.state.state_supervision_period import (
    StateSupervisionPeriodSupervisionType,
)
from recidiviz.persistence.entity.state.entities import StateIncarcerationPeriod
from recidiviz.pipelines.utils.state_utils.state_specific_supervision_delegate import (
    StateSpecificSupervisionDelegate,
)

# TODO(#29370): Consider changing this to refer to supervision_type enum values instead
# of raw text.
RELEASE_REASON_RAW_TEXT_TO_SUPERVISION_TYPE = {
    "PRB": StateSupervisionPeriodSupervisionType.PROBATION,
    "RPRB": StateSupervisionPeriodSupervisionType.PROBATION,
    "PARL": StateSupervisionPeriodSupervisionType.PAROLE,
    "PV": StateSupervisionPeriodSupervisionType.PAROLE,
    "RPAR": StateSupervisionPeriodSupervisionType.PAROLE,
    "PROL": StateSupervisionPeriodSupervisionType.PAROLE,
}


class UsNdSupervisionDelegate(StateSpecificSupervisionDelegate):
    """US_ND implementation of the supervision delegate"""

    def assessment_types_to_include_for_class(
        self, assessment_class: StateAssessmentClass
    ) -> Optional[List[StateAssessmentType]]:
        """In US_ND, only LSIR assessments are supported."""
        if assessment_class == StateAssessmentClass.RISK:
            return [StateAssessmentType.LSIR]
        return None

    def get_incarceration_period_supervision_type_at_release(
        self, incarceration_period: StateIncarcerationPeriod
    ) -> Optional[StateSupervisionPeriodSupervisionType]:
        """Calculates the post-incarceration supervision type for US_ND by evaluating the raw text fields associated
        with the release_reason.
        """

        if not incarceration_period.release_date:
            raise ValueError(
                f"No release date for incarceration period {incarceration_period.incarceration_period_id}"
            )

        if not incarceration_period.release_reason:
            raise ValueError(
                f"No release reason for incarceraation period {incarceration_period.incarceration_period_id}"
            )

        # Releases to supervision are always classified as a CONDITIONAL_RELEASE
        if (
            incarceration_period.release_reason
            != StateIncarcerationPeriodReleaseReason.CONDITIONAL_RELEASE
        ):
            return None

        release_reason_raw_text = incarceration_period.release_reason_raw_text

        if not release_reason_raw_text:
            raise ValueError(
                f"Unexpected empty release_reason_raw_text value for incarceration period "
                f"{incarceration_period.incarceration_period_id}."
            )

        supervision_type = RELEASE_REASON_RAW_TEXT_TO_SUPERVISION_TYPE.get(
            release_reason_raw_text
        )

        if not supervision_type:
            raise ValueError(
                f"Unexpected release_reason_raw_text value {release_reason_raw_text} being mapped to"
                f" {StateIncarcerationPeriodReleaseReason.CONDITIONAL_RELEASE}."
            )

        return supervision_type
