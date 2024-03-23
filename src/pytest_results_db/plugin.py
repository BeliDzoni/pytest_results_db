from __future__ import annotations

import logging
import os

import numpy as np
import pytest
from _pytest.stash import StashKey
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from .db_setup import Base
from .db_setup import ExecutionTable
from .db_setup import TestCase

stash_results = StashKey["ExtraAttachment"]()

LOGGER = logging.getLogger(__name__)


def pytest_addoption(parser):
    parser.addoption(
        "--db_path",
        action="store",
        default="",
        dest="db_path",
        help="location where db will be created",
    )
    parser.addoption(
        "--db_stack_results",
        action="store_false",
        dest="db_stack",
        help="if true results will be stacked, else db will be cleared before execution",
    )


class ExtrasAttachment:
    expected: str = ""
    result: str = ""
    html: str = ""
    text: str = ""
    picture: str = ""
    docstring: str = ""

    def __init__(self, request):
        self._request = request
        self.results: dict[str, np.array] = self._request.config.stash[stash_results]
        self.extras: dict = {}

    @property
    def test_case_name(self) -> str:
        test_name = os.environ.get("PYTEST_CURRENT_TEST", "").split("::")[-1].split("[")[0]
        if "(setup)" in test_name or "(call)" in test_name:
            return test_name.split()[0]
        return test_name

    def __setattr__(self, key, value):
        if key == "result":
            test_case_name = self.test_case_name
            if test_case_name not in self.results:
                self.results[test_case_name] = np.array([])
            self.results[test_case_name] = np.append(self.results[test_case_name], value)
        super().__setattr__(key, value)


class TestResultsDB:

    def __init__(self, config):
        self.config = config
        self.engine = None
        self.session = None

    def pytest_sessionstart(self):
        self.engine = create_engine("sqlite:///{}".format(self.config.getoption("db_path")))
        if self.config.getoption("db_stack"):
            Base.metadata.drop_all(bind=self.engine)
        Base.metadata.create_all(bind=self.engine)
        session = sessionmaker(bind=self.engine)
        self.session = session()

    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_makereport(self, item, call):
        outcome = yield
        report = outcome.get_result()

        # Check if the test was executed and determine the status
        if report.when == "call":
            record_test_result = item.funcargs.get("record_test_result", ExtrasAttachment(request=item))
            record_test_result.extras.update(
                {
                    "caplog": report.caplog,
                    "capsderr": report.capstderr,
                    "capstdout": report.capstdout,
                    "repr": report.longreprtext,
                }
            )
            docstring = self.pick_docstring(item, record_test_result)
            expected_result = self.pick_expected_results(item, record_test_result)
            markers = self.pick_markers(item)
            test_name = item.originalname
            params = getattr(getattr(item, "callspec", None), "params", {})
            test_result = TestCase(
                name=test_name,
                markers=markers,
                cls_name=item.parent.obj.__name__,
                description=docstring,
            )
            self.session.merge(test_result)
            try:
                self.session.commit()
            except IntegrityError as e:
                # Handle the error gracefully
                LOGGER.critical(f"Error: {e}")
                # Rollback the transaction if necessary
                self.session.rollback()
            except Exception as e:
                LOGGER.critical(e)
                self.session.rollback()
            executed_results = ExecutionTable(
                test_name=test_name,
                params=str(params),
                status=report.outcome,  # passed, failed, skipped ...
                duration=report.duration,
                expected=expected_result,
                result=record_test_result.result,
                html=record_test_result.html,
                text=record_test_result.text,
                picture=record_test_result.picture,
                extras=str(record_test_result.extras),
            )

            self.session.merge(executed_results)
            try:
                self.session.commit()
            except IntegrityError as e:
                # Handle the error gracefully
                LOGGER.critical(f"Error: {e}")
                # Rollback the transaction if necessary
                self.session.rollback()
            except Exception as e:
                LOGGER.critical(e)
                self.session.rollback()

    def pytest_sessionfinish(self):
        self.session.close()

    @pytest.fixture(scope="function", autouse=True)
    def record_test_result(self, request):
        extra = ExtrasAttachment(request=request)
        yield extra

    @staticmethod
    def pick_docstring(item, record_test_result):
        if record_test_result.docstring:
            return record_test_result.docstring
        test_parent = item.parent.obj
        pref = test_parent.__doc__.strip() if test_parent.__doc__ else None
        if pref:
            return pref
        test = item.obj
        suf = test.__doc__.strip() if test.__doc__ else None
        if suf:
            return suf
        return ""

    @staticmethod
    def pick_expected_results(item, record_test_result):
        if record_test_result.expected:
            return record_test_result.expected
        test_parent = item.parent.obj
        pref = getattr(test_parent, "expected", None)
        if pref:
            return pref
        return ""

    @staticmethod
    def pick_markers(item) -> str:
        markers = [marker.name for marker in item.iter_markers()]
        return " ".join(markers)


def pytest_configure(config):
    if config.getoption("db_path", None):
        config.stash[stash_results] = {}
        results_db = TestResultsDB(config)
        config.pluginmanager.register(results_db)
