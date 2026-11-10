"""The zero-skips rule: any skip or xfail fails the whole run."""

from __future__ import annotations

import pytest

PLUGIN = "tests.plugins.zero_skips"


def test_skip_fails_the_run(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        """
        import pytest

        def test_ok():
            assert True

        @pytest.mark.skip(reason="no db")
        def test_skipped():
            assert True
        """
    )
    result = pytester.runpytest_subprocess("-p", PLUGIN)
    assert result.ret == pytest.ExitCode.TESTS_FAILED
    result.stdout.fnmatch_lines(["*ZERO-SKIPS RULE VIOLATED*", "*test_skipped*"])


def test_runtime_skip_fails_the_run(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        """
        import pytest

        def test_needs_db():
            pytest.skip("postgres not reachable")
        """
    )
    result = pytester.runpytest_subprocess("-p", PLUGIN)
    assert result.ret == pytest.ExitCode.TESTS_FAILED


def test_xfail_fails_the_run(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        """
        import pytest

        @pytest.mark.xfail(reason="later")
        def test_later():
            assert False
        """
    )
    result = pytester.runpytest_subprocess("-p", PLUGIN)
    assert result.ret == pytest.ExitCode.TESTS_FAILED


def test_module_skip_fails_the_run(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        """
        import pytest

        pytest.importorskip("module_that_does_not_exist_anywhere")

        def test_never_runs():
            assert True
        """
    )
    result = pytester.runpytest_subprocess("-p", PLUGIN)
    assert result.ret == pytest.ExitCode.TESTS_FAILED


def test_clean_run_passes(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        """
        def test_ok():
            assert True
        """
    )
    result = pytester.runpytest_subprocess("-p", PLUGIN)
    assert result.ret == pytest.ExitCode.OK
