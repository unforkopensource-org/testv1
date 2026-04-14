"""JUnit XML reporter for CI integrations."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from decibench.models import SuiteResult


def format_junit_xml(result: SuiteResult) -> str:
    """Generate a JUnit XML string from a suite result."""

    testsuites = ET.Element(
        "testsuites",
        {
            "name": f"Decibench {result.suite}",
            "tests": str(result.total_scenarios),
            "failures": str(result.failed),
            "time": str(result.duration_seconds),
        },
    )

    testsuite = ET.SubElement(
        testsuites,
        "testsuite",
        {
            "name": f"Target: {result.target}",
            "tests": str(result.total_scenarios),
            "failures": str(result.failed),
            "time": str(result.duration_seconds),
            "timestamp": result.timestamp,
        },
    )

    for eval_res in result.results:
        # Each scenario is a test case
        testcase = ET.SubElement(
            testsuite,
            "testcase",
            {
                "classname": f"{result.suite}.{eval_res.scenario_id}",
                "name": eval_res.scenario_id,
                "time": str(round(eval_res.duration_ms / 1000.0, 3)),
            },
        )

        if not eval_res.passed:
            # Join all failure categories and strings
            fail_msg = "\n".join(eval_res.failures)
            fail_type = (
                ", ".join(eval_res.failure_summary)
                if eval_res.failure_summary
                else "assertion_error"
            )

            failure = ET.SubElement(
                testcase,
                "failure",
                {
                    "message": f"Score {eval_res.score:.1f}/100. Failed metrics: {fail_type}",
                    "type": fail_type,
                },
            )
            failure.text = fail_msg

    tree = ET.ElementTree(testsuites)
    ET.indent(tree, space="  ")
    return ET.tostring(testsuites, encoding="unicode")


def save_junit_xml(result: SuiteResult, path: Path) -> None:
    """Write JUnit XML out to a file."""
    xml_str = format_junit_xml(result)
    path.write_text(xml_str, encoding="utf-8")
