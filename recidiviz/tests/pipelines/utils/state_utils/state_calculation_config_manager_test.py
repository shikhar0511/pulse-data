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
"""Tests that all states with defined state-specific delegates are supported in the
state_calculation_config_manager functions."""
import datetime
import unittest
from typing import Any, Dict, List, Sequence, Type, Union, no_type_check
from unittest.mock import MagicMock

import mock

from recidiviz.persistence.entity.base_entity import Entity
from recidiviz.persistence.entity.state.entities import (
    StateAssessment,
    StateIncarcerationPeriod,
    StatePerson,
    StateStaffSupervisorPeriod,
    StateSupervisionPeriod,
)
from recidiviz.pipelines.normalization.utils.normalization_managers.incarceration_period_normalization_manager import (
    StateSpecificIncarcerationNormalizationDelegate,
)
from recidiviz.pipelines.normalization.utils.normalization_managers.supervision_period_normalization_manager import (
    StateSpecificSupervisionNormalizationDelegate,
)
from recidiviz.pipelines.normalization.utils.normalization_managers.supervision_violation_responses_normalization_manager import (
    StateSpecificViolationResponseNormalizationDelegate,
)
from recidiviz.pipelines.utils.execution_utils import TableRow
from recidiviz.pipelines.utils.state_utils import state_calculation_config_manager
from recidiviz.pipelines.utils.state_utils.state_calculation_config_manager import (
    _get_state_specific_supervision_delegate,
    get_required_state_specific_delegates,
    get_required_state_specific_metrics_producer_delegates,
    get_state_specific_case_compliance_manager,
)
from recidiviz.pipelines.utils.state_utils.state_specific_delegate import (
    StateSpecificDelegate,
)
from recidiviz.pipelines.utils.state_utils.state_specific_metrics_producer_delegate import (
    StateSpecificMetricsProducerDelegate,
)
from recidiviz.pipelines.utils.state_utils.templates.us_xx.us_xx_assessment_normalization_delegate import (
    UsXxAssessmentNormalizationDelegate,
)
from recidiviz.pipelines.utils.state_utils.templates.us_xx.us_xx_commitment_from_supervision_utils import (
    UsXxCommitmentFromSupervisionDelegate,
)
from recidiviz.pipelines.utils.state_utils.templates.us_xx.us_xx_incarceration_delegate import (
    UsXxIncarcerationDelegate,
)
from recidiviz.pipelines.utils.state_utils.templates.us_xx.us_xx_incarceration_period_normalization_delegate import (
    UsXxIncarcerationNormalizationDelegate,
)
from recidiviz.pipelines.utils.state_utils.templates.us_xx.us_xx_sentence_normalization_delegate import (
    UsXxSentenceNormalizationDelegate,
)
from recidiviz.pipelines.utils.state_utils.templates.us_xx.us_xx_staff_role_period_normalization_delegate import (
    UsXxStaffRolePeriodNormalizationDelegate,
)
from recidiviz.pipelines.utils.state_utils.templates.us_xx.us_xx_supervision_delegate import (
    UsXxSupervisionDelegate,
)
from recidiviz.pipelines.utils.state_utils.templates.us_xx.us_xx_supervision_period_normalization_delegate import (
    UsXxSupervisionNormalizationDelegate,
)
from recidiviz.pipelines.utils.state_utils.templates.us_xx.us_xx_violation_response_normalization_delegate import (
    UsXxViolationResponseNormalizationDelegate,
)
from recidiviz.pipelines.utils.state_utils.templates.us_xx.us_xx_violations_delegate import (
    UsXxViolationDelegate,
)

_DEFAULT_SUPERVISION_PERIOD_ID = 999

DEFAULT_US_MO_SENTENCE_STATUSES = [
    {
        "sentence_external_id": "1061945-20030505-7",
        "sentence_status_external_id": "1061945-20030505-7-26",
        "status_code": "35I1000",
        "status_date": "20180716",
        "status_description": "Court Probation-Revisit",
    },
]

# The state-specific delegates that should be used in state-agnostic tests
STATE_DELEGATES_FOR_TESTS: Dict[str, StateSpecificDelegate] = {
    "StateSpecificIncarcerationNormalizationDelegate": UsXxIncarcerationNormalizationDelegate(),
    "StateSpecificSupervisionNormalizationDelegate": UsXxSupervisionNormalizationDelegate(),
    "StateSpecificViolationResponseNormalizationDelegate": UsXxViolationResponseNormalizationDelegate(),
    "StateSpecificCommitmentFromSupervisionDelegate": UsXxCommitmentFromSupervisionDelegate(),
    "StateSpecificViolationDelegate": UsXxViolationDelegate(),
    "StateSpecificIncarcerationDelegate": UsXxIncarcerationDelegate(),
    "StateSpecificSupervisionDelegate": UsXxSupervisionDelegate(),
    "StateSpecificAssessmentNormalizationDelegate": UsXxAssessmentNormalizationDelegate(),
    "StateSpecificSentenceNormalizationDelegate": UsXxSentenceNormalizationDelegate(),
    "StateSpecificStaffRolePeriodNormalizationDelegate": UsXxStaffRolePeriodNormalizationDelegate(),
}


@no_type_check
def test_get_required_state_specific_delegates() -> None:
    """Tests that we can call all functions in the state_calculation_config_manager
    file with all of the state codes that we expect to be supported."""
    for state in state_calculation_config_manager.get_supported_states():
        get_required_state_specific_delegates(
            state.value,
            [
                subclass
                for subclass in StateSpecificDelegate.__subclasses__()
                if subclass is not StateSpecificMetricsProducerDelegate
            ],
            entity_kwargs={
                StateAssessment.__name__: [
                    StateAssessment.new_with_defaults(
                        state_code=state.value,
                        external_id="a1",
                    )
                ],
                StatePerson.__name__: [
                    StatePerson.new_with_defaults(state_code=state.value)
                ],
                StateIncarcerationPeriod.__name__: [
                    StateIncarcerationPeriod.new_with_defaults(
                        state_code=state.value,
                        external_id="ip1",
                    )
                ],
                StateStaffSupervisorPeriod.__name__: [
                    StateStaffSupervisorPeriod.new_with_defaults(
                        state_code=state.value,
                        external_id="SSP",
                        start_date=datetime.date(2020, 1, 2),
                        supervisor_staff_external_id="SUP1",
                        supervisor_staff_external_id_type="SUPERVISOR",
                    )
                ],
                "us_mo_sentence_statuses": DEFAULT_US_MO_SENTENCE_STATUSES,
            },
        )

        test_sp = StateSupervisionPeriod.new_with_defaults(
            state_code=state.value,
            external_id="sp1",
        )

        get_state_specific_case_compliance_manager(
            person=None,
            supervision_period=test_sp,
            case_type=None,
            start_of_supervision=None,
            assessments_by_date=None,
            supervision_contacts_by_date=None,
            violation_responses=None,
            incarceration_period_index=None,
            supervision_delegate=None,
        )

        _get_state_specific_supervision_delegate(state.value)

        for subclass in StateSpecificMetricsProducerDelegate.__subclasses__():
            get_required_state_specific_metrics_producer_delegates(
                state.value, {subclass}
            )


class TestGetRequiredStateSpecificDelegates(unittest.TestCase):
    """Tests the get_required_state_specific_delegates function."""

    @mock.patch(
        "recidiviz.pipelines.utils.state_utils.state_calculation_config_manager"
        "._get_state_specific_violation_response_normalization_delegate"
    )
    @mock.patch(
        "recidiviz.pipelines.utils.state_utils.state_calculation_config_manager"
        "._get_state_specific_supervision_period_normalization_delegate"
    )
    @mock.patch(
        "recidiviz.pipelines.utils.state_utils.state_calculation_config_manager"
        "._get_state_specific_incarceration_period_normalization_delegate"
    )
    def test_get_required_state_specific_delegates(
        self,
        get_incarceration_delegate: MagicMock,
        get_supervision_delegate: MagicMock,
        get_violation_response_delegate: MagicMock,
    ) -> None:
        get_incarceration_delegate.return_value = STATE_DELEGATES_FOR_TESTS[
            StateSpecificIncarcerationNormalizationDelegate.__name__
        ]
        get_supervision_delegate.return_value = STATE_DELEGATES_FOR_TESTS[
            StateSpecificSupervisionNormalizationDelegate.__name__
        ]
        get_violation_response_delegate.return_value = STATE_DELEGATES_FOR_TESTS[
            StateSpecificViolationResponseNormalizationDelegate.__name__
        ]

        required_delegates = [
            StateSpecificIncarcerationNormalizationDelegate,
            StateSpecificSupervisionNormalizationDelegate,
            StateSpecificViolationResponseNormalizationDelegate,
        ]
        entity_kwargs: Dict[str, Union[Sequence[Entity], List[TableRow]]] = {}

        delegates = (
            state_calculation_config_manager.get_required_state_specific_delegates(
                state_code="US_XX",
                required_delegates=required_delegates,
                entity_kwargs=entity_kwargs,
            )
        )
        expected_delegates = {
            StateSpecificIncarcerationNormalizationDelegate.__name__: STATE_DELEGATES_FOR_TESTS[
                StateSpecificIncarcerationNormalizationDelegate.__name__
            ],
            StateSpecificSupervisionNormalizationDelegate.__name__: STATE_DELEGATES_FOR_TESTS[
                StateSpecificSupervisionNormalizationDelegate.__name__
            ],
            StateSpecificViolationResponseNormalizationDelegate.__name__: STATE_DELEGATES_FOR_TESTS[
                StateSpecificViolationResponseNormalizationDelegate.__name__
            ],
        }

        self.assertEqual(expected_delegates, delegates)

    def test_get_required_state_specific_delegates_no_delegates(self) -> None:
        required_delegates: List[Type[StateSpecificDelegate]] = []
        entity_kwargs: Dict[str, Union[Sequence[Entity], List[TableRow]]] = {}
        delegates = (
            state_calculation_config_manager.get_required_state_specific_delegates(
                state_code="US_XX",
                required_delegates=required_delegates,
                entity_kwargs=entity_kwargs,
            )
        )

        expected_delegates: Dict[str, Any] = {}

        self.assertEqual(expected_delegates, delegates)
