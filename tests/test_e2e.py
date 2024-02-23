from __future__ import annotations

import sqlite3

import pandas as pd
from _pytest.pytester import RunResult

pytest_plugins = ("pytester",)


def run(pytester, db_path="db.db", cmd_flags=None) -> tuple[pd.DataFrame, pd.DataFrame, RunResult]:
    cmd_flags = cmd_flags or []
    db_path = pytester.path.joinpath(db_path)
    results = pytester.runpytest("--db_path", db_path, *cmd_flags)
    conn = sqlite3.connect(db_path)
    query_cases = "SELECT * FROM test_cases"
    query_execution = "SELECT * FROM execution_table"
    db_cases = pd.read_sql_query(query_cases, conn)
    db_execution = pd.read_sql_query(query_execution, conn)
    conn.close()
    return db_cases, db_execution, results


def test_passed_failed_skipped(pytester):
    test_dict = {
        "passed": "test_pass",
        "failed": "test_failed",
        "skipped": "test_skipped",
    }
    pytester.makepyfile(
        f"""
        import pytest
        def {test_dict['passed']}():
            ...

        def {test_dict['failed']}():
            assert False

        def {test_dict['skipped']}():
            pytest.skip("skipped")
        """
    )
    db_cases, db_execution, results = run(pytester)
    results.assert_outcomes(passed=1, skipped=1, failed=1)
    assert db_execution.status.to_list() == list(test_dict.keys())
    assert db_execution.test_name.to_list() == list(test_dict.values())
    assert db_cases.name.to_list() == list(test_dict.values())


def test_parametrized(pytester):
    n = 3
    parametrize_list = list(range(n))
    params_list = [str({"a": i}) for i in parametrize_list]

    pytester.makepyfile(
        f"""
        import pytest
        @pytest.mark.parametrize("a", {parametrize_list})
        def test_parametrized(a):
            print(a)
        """
    )
    _, db_execution, results = run(pytester)
    results.assert_outcomes(passed=n)
    assert db_execution.params.to_list() == list(params_list)


def test_docstring(pytester):
    docstring = "Docstring."
    test_name = "test_docstring"
    class_name = "TestDocstring"
    pytester.makepyfile(
        f'''
        def {test_name}():
            """
            {docstring}
            """
            ...
        class {class_name}:
            """
            {docstring}
            """
            def {test_name}(self):
                ...
        '''
    )
    db_cases, _, _ = run(pytester)
    assert db_cases.description.to_list() == [docstring] * 2
    assert db_cases.cls_name.to_list() == [test_name, class_name]
    assert db_cases.name.to_list() == [test_name] * 2


def test_marker(pytester):
    marker = "test_marker"
    pytester.makepyfile(
        f"""
        import pytest
        @pytest.mark.{marker}
        def test_marker():
            ...
        """
    )
    db_cases, _, _ = run(pytester)
    assert db_cases.markers.to_list() == [marker]


def test_xdist(pytester):
    n = 100
    pytester.makepyfile(
        f"""
        import pytest
        @pytest.mark.parametrize("a", list(range({n})))
        def test_1(a):
            pass
        """
    )
    db_cases, db_execution, result = run(pytester, cmd_flags=["-n", "4"])
    result.assert_outcomes(passed=n)
    assert [worker for worker in result.outlines if "worker" in worker]  # check if xdist is working
    assert n == db_execution.shape[0]
    assert 1 == db_cases.shape[0]


def test_stack_results(pytester):
    pytester.makepyfile(
        """
            def test_1():
                pass
            """
    )
    # First execution
    run(pytester, cmd_flags=["--db_stack_results"])
    # 2nd execution
    db_cases, db_execution, result = run(pytester, cmd_flags=["--db_stack_results"])
    result.assert_outcomes(passed=1)
    assert 2 == db_execution.shape[0]
    assert 1 == db_cases.shape[0]


def test_expected(pytester):
    pytester.makepyfile(
        """
            def test_1(record_test_result):
                record_test_result.expected = 1
                record_test_result.result = 1
                assert record_test_result.expected == record_test_result.result
            """
    )
    db_cases, db_execution, result = run(pytester)
    assert db_execution.result.to_list() == ['1']
    assert db_execution.expected.to_list() == ['1']

