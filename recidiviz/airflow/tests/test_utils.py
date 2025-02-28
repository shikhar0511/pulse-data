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
"""Test utilities for DAG tests"""
import logging
import os
import re
import sys
import unittest
from datetime import datetime
from typing import Any, Dict, List, Optional, Set
from unittest.mock import patch

import attr
from airflow import DAG, settings
from airflow.models import BaseOperator, DagRun, TaskInstance
from airflow.utils import timezone
from airflow.utils.context import Context
from airflow.utils.db import initdb, resetdb
from airflow.utils.state import DagRunState, State, TaskInstanceState
from airflow.utils.types import DagRunType
from sqlalchemy.orm import Session

from recidiviz import airflow as recidiviz_airflow_module
from recidiviz.tools.postgres import local_postgres_helpers

AIRFLOW_WORKING_DIRECTORY = os.path.dirname(recidiviz_airflow_module.__file__)
DAG_FOLDER = os.path.abspath(os.path.join(AIRFLOW_WORKING_DIRECTORY, "dags"))

_FAKE_RUN_ID = "abc123"


def execute_task(dag: DAG, task: BaseOperator) -> Any:
    """Executes a task in a given DAG, passing the appropriate context dictionary."""
    execution_date = datetime.now()
    context = Context(
        {
            "task": task,
            "dag_run": DagRun(
                dag_id=dag.dag_id, execution_date=execution_date, run_id=_FAKE_RUN_ID
            ),
            "ti": TaskInstance(
                task=task, execution_date=execution_date, run_id=_FAKE_RUN_ID
            ),
        }
    )
    return task.execute(context)


@attr.s(auto_attribs=True)
class DagTestResult:
    """Stores the results of a dag test run"""

    dag_run_state: DagRunState

    failure_messages: Dict[str, str]
    """A dictionary of task_id -> failure message if the task failed"""


class AirflowIntegrationTest(unittest.TestCase):
    """Sets up the airflow database and provides a SQLAlchemy session builder"""

    # Stores the location of the postgres DB for this test run
    temp_db_dir: Optional[str]
    environment_patcher: Any

    @classmethod
    def setUpClass(cls) -> None:
        cls.temp_db_dir = local_postgres_helpers.start_on_disk_postgresql_database()
        cls.environment_patcher = patch(
            "os.environ",
            {
                "AIRFLOW__DATABASE__SQL_ALCHEMY_CONN": local_postgres_helpers.on_disk_postgres_db_url(),
            },
        )
        cls.environment_patcher.start()

        # Configure settings.Session() to use the new on-disk postgres
        settings.initialize()

    @classmethod
    def tearDownClass(cls) -> None:
        local_postgres_helpers.stop_and_clear_on_disk_postgresql_database(
            cls.temp_db_dir
        )
        cls.environment_patcher.stop()

    def setUp(self) -> None:
        self.engine = settings.engine
        initdb(load_connections=False)

    def tearDown(self) -> None:
        resetdb(skip_init=True)
        self.engine.dispose()

    def run_dag_test(
        self,
        dag: DAG,
        session: Session,
        run_conf: Optional[Dict[str, Any]] = None,
        expected_failure_ids: Optional[List[str]] = None,
        expected_skipped_ids: Optional[List[str]] = None,
        skip_checking_task_statuses: Optional[bool] = False,
    ) -> DagTestResult:
        """
        A Modified version of 'dag.test'. Will run the full dag to allow
        looking up statuses in the postgres database. `expected_failure_ids` and `expected_skipped_ids`
        take regexes. Failure messages are stored in self.failure_messages.
        """

        failure_messages: Dict[str, str] = {}

        def add_logger_if_needed(ti: TaskInstance) -> None:
            """
            Add a formatted logger to the taskinstance so all logs are surfaced to the command line instead
            of into a task file. Since this is a local test run, it is much better for the user to see logs
            in the command line, rather than needing to search for a log file.
            Args:
                ti: The taskinstance that will receive a logger

            """
            formatter = logging.Formatter(
                "[%(asctime)s] {%(filename)s:%(lineno)d} %(levelname)s - %(message)s"
            )
            handler = logging.StreamHandler(sys.stdout)
            handler.level = logging.INFO
            handler.setFormatter(formatter)
            # only add log handler once
            if not any(isinstance(h, logging.StreamHandler) for h in ti.log.handlers):
                dag.log.debug("Adding Streamhandler to taskinstance %s", ti.task_id)
                ti.log.addHandler(handler)

        execution_date = timezone.utcnow()
        dag.log.debug(
            "Clearing existing task instances for execution date %s", execution_date
        )
        dag.clear(
            start_date=execution_date,
            end_date=execution_date,
            dag_run_state=False,  # type: ignore
            session=session,
        )

        dag.log.debug("Getting dagrun for dag %s", dag.dag_id)
        dr: DagRun = self._get_or_create_dagrun(
            dag=dag,
            session=session,
            start_date=execution_date,
            execution_date=execution_date,
            run_id=DagRun.generate_run_id(DagRunType.MANUAL, execution_date),
            conf=run_conf,
        )

        tasks = dag.task_dict
        dag.log.debug("starting dagrun")
        # Instead of starting a scheduler, we run the minimal loop possible to check
        # for task readiness and dependency management. This is notably faster
        # than creating a BackfillJob and allows us to surface logs to the user
        while dr.state == State.RUNNING:
            schedulable_tis, _ = dr.update_state(session=session)
            for ti in schedulable_tis:
                add_logger_if_needed(ti)
                ti.task = tasks[ti.task_id]
                failure_message = self._run_task(ti, session)
                if failure_message:
                    failure_messages[ti.task_id] = failure_message

        dag.run(ignore_first_depends_on_past=True, verbose=True)

        if not skip_checking_task_statuses:
            self._check_dag_task_statuses(
                dag, session, expected_failure_ids, expected_skipped_ids
            )

        return DagTestResult(self._get_dag_run_state(session), failure_messages)

    def _check_dag_task_statuses(
        self,
        dag: DAG,
        session: Session,
        expected_failure_ids: Optional[List[str]] = None,
        expected_skipped_ids: Optional[List[str]] = None,
    ) -> None:
        """
        Check that the task statuses are as expected. If expected_failure_ids or expected_skipped_ids are
        provided, then the task statuses must match the expected statuses. Otherwise, the task statuses
        must be SUCCESS.
        """
        expected_failure_task_ids = _find_task_ids_for_given_search_regexes(
            dag, expected_failure_ids or []
        )
        expected_skipped_task_ids = _find_task_ids_for_given_search_regexes(
            dag, expected_skipped_ids or []
        )

        for task_instance in dag.tasks:
            task_state = self.get_task_instance_state(task_instance.task_id, session)
            if (
                task_state == TaskInstanceState.SKIPPED
                and task_instance.task_id not in expected_skipped_task_ids
            ):
                raise ValueError(
                    f"Task [{task_instance.task_id}] was skipped unexpectedly"
                )
            if (
                task_state
                in [TaskInstanceState.FAILED, TaskInstanceState.UPSTREAM_FAILED]
                and task_instance.task_id not in expected_failure_task_ids
            ):
                raise ValueError(f"Task [{task_instance.task_id}] failed unexpectedly")
            if (
                task_state == TaskInstanceState.SUCCESS
                and task_instance.task_id
                in expected_failure_task_ids | expected_skipped_task_ids
            ):
                raise ValueError(
                    f"Task [{task_instance.task_id}] succeeded unexpectedly"
                )

            if task_state not in [
                TaskInstanceState.SUCCESS,
                TaskInstanceState.SKIPPED,
                TaskInstanceState.FAILED,
                TaskInstanceState.UPSTREAM_FAILED,
            ]:
                raise ValueError(
                    f"Task [{task_instance.task_id}] has an unexpected state: {task_state}"
                )

    def _get_or_create_dagrun(
        self,
        dag: DAG,
        session: Session,
        conf: Optional[Dict[Any, Any]],
        start_date: datetime,
        execution_date: datetime,
        run_id: str,
    ) -> DagRun:
        """
        Create a DAGRun, but only after clearing the previous instance of said dagrun to prevent collisions.
        This is a modified version of airflow.models.dag._get_or_create_dagrun
        """
        logging.info("dagrun id: %s", dag.dag_id)
        dr: DagRun = (
            session.query(DagRun)
            .filter(
                DagRun.dag_id == dag.dag_id, DagRun.execution_date == execution_date
            )
            .first()
        )
        if dr:
            session.delete(dr)
            session.commit()
        dr = dag.create_dagrun(
            state=DagRunState.RUNNING,
            execution_date=execution_date,
            run_id=run_id,
            start_date=start_date or execution_date,
            session=session,
            conf=conf,  # type: ignore
            data_interval=(execution_date, execution_date),
        )
        logging.info("created dagrun %s", str(dr))
        return dr

    def _run_task(self, ti: TaskInstance, session: Session) -> Optional[str]:
        """
        Run a single task instance, and push result to Xcom for downstream tasks. This is a modified version of
        airflow.models.dag._run_task. Returns a failure message if the task fails.
        """
        logging.info("*****************************************************")
        if ti.map_index > 0:
            logging.info("Running task %s index %d", ti.task_id, ti.map_index)
        else:
            logging.info("Running task %s", ti.task_id)
        try:
            ti._run_raw_task(session=session)  # pylint: disable=protected-access
            session.flush()
            logging.info("%s ran successfully!", ti.task_id)
        except Exception as e:
            logging.info(e)
            return str(e)
        logging.info("*****************************************************")
        return None

    def _get_dag_run_state(self, session: Session) -> DagRunState:
        """Get the state of the most recent dag run."""
        rows = session.query(DagRun.state).first()
        if not rows:
            raise ValueError("DagRun not found")
        return DagRunState(rows[0])

    def get_task_instance_state(
        self, task_id: str, session: Session
    ) -> TaskInstanceState:
        """Get the state of the task instance with task_id from the most recent dag run."""
        rows = (
            session.query(TaskInstance.state)
            .filter(TaskInstance.task_id == task_id)
            .first()
        )
        if not rows:
            raise ValueError(f"Task [{task_id}] not found")
        return TaskInstanceState(rows[0])


def _find_task_ids_for_given_search_regexes(
    dag_to_search: DAG, search_regexes: List[str]
) -> Set[str]:
    """
    Returns a set of task ids that match the given search regexes. All task ids that match
    any of the regexes will be returned. Note that regex search ignores case sensitivity.
    """
    found_task_ids = set()

    for search_regex in search_regexes or []:
        matching_task_ids = set()
        for task_id in dag_to_search.task_dict:
            if re.search(search_regex, task_id, re.I):
                matching_task_ids.add(task_id)
        if len(matching_task_ids) == 0:
            raise ValueError(
                f"Could not find task or task group with id: {search_regex}"
            )
        found_task_ids.update(matching_task_ids)

    return found_task_ids
