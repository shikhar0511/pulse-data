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
"""Tests for the state dataflow pipeline."""

import os
import unittest
from datetime import datetime
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import yaml
from airflow.models import BaseOperator
from airflow.models.dag import DAG, dag
from airflow.operators.empty import EmptyOperator
from airflow.utils.state import DagRunState
from sqlalchemy.orm import Session

from recidiviz.airflow.dags.calculation.dataflow.single_ingest_pipeline_group import (
    _should_run_based_on_watermarks,
    create_single_ingest_pipeline_group,
)
from recidiviz.airflow.dags.operators.recidiviz_dataflow_operator import (
    RecidivizDataflowFlexTemplateOperator,
)
from recidiviz.airflow.tests import fixtures
from recidiviz.airflow.tests.test_utils import AirflowIntegrationTest
from recidiviz.airflow.tests.utils.dag_helper_functions import (
    FakeFailureOperator,
    fake_failure_task,
    fake_operator_constructor,
    fake_operator_with_return_value,
)
from recidiviz.common.constants.states import StateCode
from recidiviz.pipelines.ingest.pipeline_utils import (
    DEFAULT_PIPELINE_REGIONS_BY_STATE_CODE,
)
from recidiviz.utils.environment import GCPEnvironment

# Need a disable pointless statement because Python views the chaining operator ('>>') as a "pointless" statement
# pylint: disable=W0104 pointless-statement

# Need a disable expression-not-assigned because the chaining ('>>') doesn't need expressions to be assigned
# pylint: disable=W0106 expression-not-assigned

_PROJECT_ID = "recidiviz-testing"
_TEST_DAG_ID = "test_single_ingest_pipeline_group"
_DOWNSTREAM_TASK_ID = "downstream_task"


def _create_test_single_ingest_pipeline_group_dag(state_code: StateCode) -> DAG:
    @dag(
        dag_id=_TEST_DAG_ID,
        start_date=datetime(2022, 1, 1),
        schedule=None,
        catchup=False,
    )
    def test_single_ingest_pipeline_group_dag() -> None:
        create_single_ingest_pipeline_group(state_code) >> EmptyOperator(
            task_id=_DOWNSTREAM_TASK_ID
        )

    return test_single_ingest_pipeline_group_dag()


@patch.dict(
    DEFAULT_PIPELINE_REGIONS_BY_STATE_CODE,
    values={StateCode.US_XX: "us-east1-test"},
)
class TestSingleIngestPipelineGroup(unittest.TestCase):
    """Tests for the single ingest pipeline group ."""

    entrypoint_args_fixture: Dict[str, List[str]] = {}

    @classmethod
    def setUpClass(cls) -> None:
        with open(
            os.path.join(os.path.dirname(fixtures.__file__), "./entrypoints_args.yaml"),
            "r",
            encoding="utf-8",
        ) as fixture_file:
            cls.entrypoint_args_fixture = yaml.safe_load(fixture_file)

    def setUp(self) -> None:
        self.environment_patcher = patch(
            "os.environ",
            {
                "GCP_PROJECT": _PROJECT_ID,
            },
        )
        self.environment_patcher.start()
        self.project_environment_patcher = patch(
            "recidiviz.utils.environment.get_environment_for_project",
            return_value=GCPEnvironment.STAGING,
        )
        self.project_environment_patcher.start()

    def tearDown(self) -> None:
        self.environment_patcher.stop()
        self.project_environment_patcher.stop()

    def test_dataflow_pipeline_task_exists(self) -> None:
        """Tests that dataflow_pipeline triggers the proper script."""

        test_dag = _create_test_single_ingest_pipeline_group_dag(StateCode.US_XX)

        task_group_id = "us_xx_dataflow.us-xx-ingest-primary"
        dataflow_pipeline_task = test_dag.get_task(f"{task_group_id}.run_pipeline")

        if not isinstance(
            dataflow_pipeline_task, RecidivizDataflowFlexTemplateOperator
        ):
            raise ValueError(
                f"Expected type RecidivizDataflowFlexTemplateOperator, found "
                f"[{type(dataflow_pipeline_task)}]."
            )

    def test_dataflow_pipeline_task(self) -> None:
        """Tests that dataflow_pipeline get the expected arguments."""

        test_dag = _create_test_single_ingest_pipeline_group_dag(StateCode.US_XX)
        task_group_id = "us_xx_dataflow.us-xx-ingest-primary"
        task: RecidivizDataflowFlexTemplateOperator = test_dag.get_task(  # type: ignore
            f"{task_group_id}.run_pipeline"
        )

        self.assertEqual(task.location, "us-east1-test")
        self.assertEqual(task.project_id, _PROJECT_ID)
        self.assertEqual(task.body.operator.task_id, f"{task_group_id}.create_flex_template")  # type: ignore


def _fake_failure_execute(*args: Any, **kwargs: Any) -> None:
    raise ValueError("Fake failure")


def _fake_pod_operator(*args: Any, **kwargs: Any) -> BaseOperator:
    if "--entrypoint=IngestPipelineShouldRunInDagEntrypoint" in kwargs["arguments"]:
        return fake_operator_with_return_value(True)(*args, **kwargs)

    return fake_operator_constructor(*args, **kwargs)


def _fake_pod_operator_ingest_pipeline_should_run_in_dag_false(
    *args: Any, **kwargs: Any
) -> BaseOperator:
    if "--entrypoint=IngestPipelineShouldRunInDagEntrypoint" in kwargs["arguments"]:
        return fake_operator_with_return_value(False)(*args, **kwargs)

    return fake_operator_constructor(*args, **kwargs)


@patch.dict(
    DEFAULT_PIPELINE_REGIONS_BY_STATE_CODE,
    values={StateCode.US_XX: "us-east1-test"},
)
class TestSingleIngestPipelineGroupIntegration(AirflowIntegrationTest):
    """Tests for the single ingest pipeline group ."""

    def setUp(self) -> None:
        super().setUp()
        self.environment_patcher = patch(
            "os.environ",
            {
                "GCP_PROJECT": _PROJECT_ID,
            },
        )
        self.environment_patcher.start()

        self.kubernetes_pod_operator_patcher = patch(
            "recidiviz.airflow.dags.calculation.dataflow.single_ingest_pipeline_group.build_kubernetes_pod_task",
            side_effect=_fake_pod_operator,
        )
        self.mock_kubernetes_pod_operator = self.kubernetes_pod_operator_patcher.start()

        self.cloud_sql_query_operator_patcher = patch(
            "recidiviz.airflow.dags.calculation.dataflow.single_ingest_pipeline_group.CloudSqlQueryOperator",
            side_effect=fake_operator_with_return_value({}),
        )
        self.cloud_sql_query_operator_patcher.start()

        self.recidiviz_dataflow_operator_patcher = patch(
            "recidiviz.airflow.dags.utils.dataflow_pipeline_group.RecidivizDataflowFlexTemplateOperator",
            side_effect=fake_operator_constructor,
        )
        self.mock_dataflow_operator = self.recidiviz_dataflow_operator_patcher.start()

    def tearDown(self) -> None:
        self.environment_patcher.stop()
        self.kubernetes_pod_operator_patcher.stop()
        self.cloud_sql_query_operator_patcher.stop()
        self.recidiviz_dataflow_operator_patcher.stop()
        super().tearDown()

    def test_single_ingest_pipeline_group(self) -> None:
        test_dag = _create_test_single_ingest_pipeline_group_dag(StateCode.US_XX)
        with Session(bind=self.engine) as session:
            result = self.run_dag_test(test_dag, session)
            self.assertEqual(DagRunState.SUCCESS, result.dag_run_state)

    def test_ingest_pipeline_should_run_in_dag_false(self) -> None:
        self.mock_kubernetes_pod_operator.side_effect = (
            _fake_pod_operator_ingest_pipeline_should_run_in_dag_false
        )

        test_dag = _create_test_single_ingest_pipeline_group_dag(StateCode.US_XX)
        with Session(bind=self.engine) as session:
            result = self.run_dag_test(
                test_dag,
                session,
                expected_skipped_ids=[
                    r".*get_max_update_datetimes",
                    r".*get_watermarks",
                    r".*should_run_based_on_watermarks",
                    r".*verify_raw_data_flashing_not_in_progress",
                    r"us_xx_dataflow\.us-xx-ingest-primary.*",
                    r".*write_ingest_job_completion",
                    r".*write_upper_bounds",
                    _DOWNSTREAM_TASK_ID,
                ],
            )
            self.assertEqual(DagRunState.SUCCESS, result.dag_run_state)

    @patch(
        "recidiviz.airflow.dags.calculation.dataflow.single_ingest_pipeline_group._should_run_based_on_watermarks"
    )
    def test_initialize_dataflow_pipeline_short_circuits_when_watermark_datetime_greater_than_max_update_datetime(
        self,
        mock_should_run_based_on_watermarks: MagicMock,
    ) -> None:
        mock_should_run_based_on_watermarks.side_effect = (
            lambda watermarks, max_update_datetimes: _should_run_based_on_watermarks(
                watermarks={"test_file_tag": "2023-01-26 00:00:0.000000+00"},
                max_update_datetimes={"test_file_tag": "2023-01-25 00:00:0.000000+00"},
            )
        )

        test_dag = _create_test_single_ingest_pipeline_group_dag(StateCode.US_XX)

        with Session(bind=self.engine) as session:
            result = self.run_dag_test(
                test_dag,
                session,
                expected_skipped_ids=[
                    r".*verify_raw_data_flashing_not_in_progress",
                    r"us_xx_dataflow\.us-xx-ingest-primary.*",
                    r".*write_ingest_job_completion",
                    r".*write_upper_bounds",
                    _DOWNSTREAM_TASK_ID,
                ],
            )
            self.assertEqual(DagRunState.SUCCESS, result.dag_run_state)

    @patch(
        "recidiviz.airflow.dags.calculation.dataflow.single_ingest_pipeline_group._verify_raw_data_flashing_not_in_progress"
    )
    def test_failed_verify_raw_data_flashing_not_in_progress(
        self, mock_verify_raw_data_flashing_not_in_progress: MagicMock
    ) -> None:
        mock_verify_raw_data_flashing_not_in_progress.side_effect = (
            lambda _state_code: fake_failure_task(
                task_id="verify_raw_data_flashing_not_in_progress"
            )
        )

        test_dag = _create_test_single_ingest_pipeline_group_dag(StateCode.US_XX)

        with Session(bind=self.engine) as session:
            result = self.run_dag_test(
                test_dag,
                session,
                expected_failure_ids=[
                    r".*verify_raw_data_flashing_not_in_progress",
                    r"us_xx_dataflow\.us-xx-ingest-primary.*",
                    r".*write_ingest_job_completion",
                    r".*write_upper_bounds",
                    _DOWNSTREAM_TASK_ID,
                ],
            )
            self.assertEqual(DagRunState.FAILED, result.dag_run_state)

    @patch(
        "recidiviz.airflow.dags.calculation.dataflow.single_ingest_pipeline_group._should_run_based_on_watermarks"
    )
    def test_initialize_dataflow_pipeline_when_watermark_datetime_less_than_max_update_datetime(
        self,
        mock_should_run_based_on_watermarks: MagicMock,
    ) -> None:
        mock_should_run_based_on_watermarks.side_effect = (
            lambda watermarks, max_update_datetimes: _should_run_based_on_watermarks(
                watermarks={"test_file_tag": "2023-01-24 00:00:0.000000+00"},
                max_update_datetimes={"test_file_tag": "2023-01-25 00:00:0.000000+00"},
            )
        )

        test_dag = _create_test_single_ingest_pipeline_group_dag(StateCode.US_XX)

        with Session(bind=self.engine) as session:
            result = self.run_dag_test(
                test_dag,
                session,
            )
            self.assertEqual(DagRunState.SUCCESS, result.dag_run_state)

    def test_failed_dataflow_pipeline(self) -> None:
        self.mock_dataflow_operator.side_effect = FakeFailureOperator

        test_dag = _create_test_single_ingest_pipeline_group_dag(StateCode.US_XX)

        with Session(bind=self.engine) as session:
            result = self.run_dag_test(
                test_dag,
                session,
                expected_failure_ids=[
                    r"us_xx_dataflow\.us-xx-ingest-primary\.run_pipeline",
                    r".*write_ingest_job_completion",
                    r".*write_upper_bounds",
                    _DOWNSTREAM_TASK_ID,
                ],
            )
            self.assertEqual(DagRunState.FAILED, result.dag_run_state)

    def test_failed_tasks_fail_group(self) -> None:
        """
        Tests that if any task in the group fails, the entire group fails.
        """
        test_dag = _create_test_single_ingest_pipeline_group_dag(StateCode.US_XX)

        task_ids_to_fail = [
            task.task_id
            for task in test_dag.task_group_dict[
                f"{StateCode.US_XX.value.lower()}_dataflow"
            ]
        ]

        with Session(bind=self.engine) as session:
            for task_id in task_ids_to_fail:
                test_dag = _create_test_single_ingest_pipeline_group_dag(
                    StateCode.US_XX
                )
                task = test_dag.get_task(task_id)
                old_execute_function = task.execute
                task.execute = _fake_failure_execute
                result = self.run_dag_test(
                    test_dag,
                    session,
                    skip_checking_task_statuses=True,
                )
                task.execute = old_execute_function
                self.assertEqual(
                    DagRunState.FAILED,
                    result.dag_run_state,
                    f"Incorrect dag run state when failing task: {task.task_id}",
                )
                self.assertIn(
                    task.task_id,
                    result.failure_messages,
                )
                self.assertEqual(
                    result.failure_messages[task.task_id],
                    "Fake failure",
                )
