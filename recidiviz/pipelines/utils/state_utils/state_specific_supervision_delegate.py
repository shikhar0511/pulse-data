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
"""Contains the StateSpecificSupervisionDelegate, the interface
for state-specific decisions involved in categorizing various attributes of
supervision."""
# pylint: disable=unused-argument
import abc
from datetime import date
from typing import List, Optional, Tuple

from recidiviz.common.constants.state.state_assessment import (
    StateAssessmentClass,
    StateAssessmentLevel,
    StateAssessmentType,
)
from recidiviz.common.constants.state.state_supervision_period import (
    StateSupervisionPeriodSupervisionType,
)
from recidiviz.common.date import DateRange, DateRangeDiff
from recidiviz.persistence.entity.state.entities import (
    StateIncarcerationPeriod,
    StateSupervisionPeriod,
)
from recidiviz.persistence.entity.state.normalized_entities import (
    NormalizedStateIncarcerationSentence,
    NormalizedStateSupervisionPeriod,
    NormalizedStateSupervisionSentence,
)
from recidiviz.pipelines.utils.state_utils.state_specific_delegate import (
    StateSpecificDelegate,
)


class StateSpecificSupervisionDelegate(abc.ABC, StateSpecificDelegate):
    """Interface for state-specific decisions involved in categorizing various attributes of supervision."""

    def supervision_types_mutually_exclusive(self) -> bool:
        """For some states, we want to track people on DUAL supervision as mutually exclusive from the groups of people on
        either PAROLE and PROBATION. For others, a person can be on multiple types of supervision simultaneously
        and contribute to counts for both types.

        Default behavior is that supervision types are *not* mutually exclusive, meaning a person can be on multiple types of supervision simultaneously.

        Returns whether our calculations should consider supervision types as distinct for the given state_code.
        """
        return False

    # TODO(#19343): Once we are able to remove this delegate, we should be able to
    #  remove the custom handling of PA level 2 locations in
    #  most_recent_dataflow_metrics.py.
    def supervision_location_from_supervision_site(
        self,
        supervision_site: Optional[str],
    ) -> Tuple[Optional[str], Optional[str]]:
        """Retrieves level 1 and level 2 location information from a supervision site.
        By default, returns the |supervision_site| as the level 1 location, and uses the
        supervision site to retrieve the level 2 information from the reference view.

        !! Disclaimer !! This code makes the assumption that the value stored in
        supervision_site is the level_1_supervision_location_external_id. If there is
        other info packed into the supervision_site field, this function must be overridden
        in the state-specific implementation of this delegate.
        """
        # TODO(#3829): Remove this helper once we've built level 1/level 2 supervision
        #  location distinction directly into our schema.
        level_1_supervision_location = supervision_site or None
        level_2_supervision_location = None

        return level_1_supervision_location, level_2_supervision_location

    def supervision_period_in_supervision_population_in_non_excluded_date_range(
        self,
        supervision_period: NormalizedStateSupervisionPeriod,
    ) -> bool:
        """Returns False if there is state-specific information to indicate that the supervision period should not count
        towards the supervision population in the date range.

        This function should only be called for a date range where the person does not have any overlapping incarceration
        that prevents the person from being counted simultaneously in the supervision population.

        By default returns True.
        """
        return True

    def get_index_of_first_reliable_supervision_assessment(self) -> int:
        """Some states rely on the first-reassessment (the second assessment) instead of the first assessment when comparing
        terminating assessment scores to a score at the beginning of someone's supervision.

        Default behavior is to return 1, the index of the second assessment."""
        # TODO(#2782): Investigate whether to update this logic
        return 1

    @abc.abstractmethod
    def assessment_types_to_include_for_class(
        self, assessment_class: StateAssessmentClass
    ) -> Optional[List[StateAssessmentType]]:
        """Defines the assessment types to refer to in calculations for a given
        assessment class. Each state needs to override this with the assessment type
        (e.g. LSIR) that they support."""

    def set_lsir_assessment_score_bucket(
        self,
        assessment_score: Optional[int],
        assessment_level: Optional[StateAssessmentLevel],
    ) -> Optional[str]:
        """This determines the logic for defining LSIR score buckets, for states
        that use LSIR as the assessment of choice. States may override this logic
        based on interpretations of LSIR scores that are different from the default
        score ranges."""
        if assessment_score:
            if assessment_score < 24:
                return "0-23"
            if assessment_score <= 29:
                return "24-29"
            if assessment_score <= 38:
                return "30-38"
            return "39+"
        return None

    def get_incarceration_period_supervision_type_at_release(
        self, incarceration_period: StateIncarcerationPeriod
    ) -> Optional[StateSupervisionPeriodSupervisionType]:
        """For some states, we may need to look at the incarceration period to determine
        the supervision type upon release. By default, returns None, as it's assumed
        we will use the supervision period's supervision type that corresponds date-wise.
        """
        return None

    def get_projected_completion_date(
        self,
        supervision_period: StateSupervisionPeriod,
        incarceration_sentences: List[NormalizedStateIncarcerationSentence],
        supervision_sentences: List[NormalizedStateSupervisionSentence],
    ) -> Optional[date]:
        """Returns the projected completion date. Because supervision periods have
        different relationships with incarceration and supervision sentences, we consider
        the projected completion date to be the latest projected_completion_date /
        projected_max_release_date of all sentences that overlap with the given period.
        """
        if not supervision_sentences and not incarceration_sentences:
            return None

        relevant_max_dates = [
            incarceration_sentence.projected_max_release_date
            for incarceration_sentence in incarceration_sentences
            if incarceration_sentence.effective_date
            and DateRangeDiff(
                supervision_period.duration,
                DateRange.from_maybe_open_range(
                    incarceration_sentence.effective_date,
                    incarceration_sentence.completion_date,
                ),
            ).overlapping_range
            and incarceration_sentence.projected_max_release_date
        ] + [
            supervision_sentence.projected_completion_date
            for supervision_sentence in supervision_sentences
            if supervision_sentence.effective_date
            and DateRangeDiff(
                supervision_period.duration,
                DateRange.from_maybe_open_range(
                    supervision_sentence.effective_date,
                    supervision_sentence.completion_date,
                ),
            ).overlapping_range
            and supervision_sentence.projected_completion_date
        ]

        return max(relevant_max_dates) if relevant_max_dates else None
