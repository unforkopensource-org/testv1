from decibench.models import EvalResult, SuiteResult
from decibench.reporters.junit import format_junit_xml


def test_junit_format_no_failures():
    result = SuiteResult(
        suite="mock", target="demo", decibench_score=100.0, total_scenarios=1, passed=1, failed=0,
        results=[
            EvalResult(scenario_id="scen-1", passed=True, score=100.0, failures=[])
        ]
    )

    xml = format_junit_xml(result)
    assert "<testsuites" in xml
    assert 'name="Decibench mock"' in xml
    assert 'failures="0"' in xml
    assert "<testsuite" in xml
    assert "<testcase" in xml
    assert "<failure" not in xml

def test_junit_format_with_failures():
    result = SuiteResult(
        suite="mock", target="demo", decibench_score=50.0, total_scenarios=2, passed=1, failed=1,
        results=[
            EvalResult(
                scenario_id="scen-2",
                passed=False,
                score=0.0,
                failures=["Latency took too long"],
                failure_summary=["latency"],
            )
        ]
    )

    xml = format_junit_xml(result)
    assert 'failures="1"' in xml
    assert '<failure' in xml
    assert 'Latency took too long' in xml
    assert 'type="latency"' in xml
