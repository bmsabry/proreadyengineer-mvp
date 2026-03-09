#!/usr/bin/env python3
"""
Test Runner for ProReadyEngineer Backend

Usage:
    python test_runner.py [options]

Options:
    --unit              Run only unit tests
    --integration       Run only integration tests
    --e2e               Run only E2E tests
    --all               Run all tests (default)
    --coverage          Generate coverage report
    --verbose, -v       Verbose output
    --fail-fast         Stop on first failure
    --match PATTERN     Run tests matching pattern
    --ci                CI/CD mode (strict exit codes)
    --html              Generate HTML coverage report
    --xml               Generate XML coverage report for CI
"""

import sys
import os
import subprocess
import argparse
from pathlib import Path


# Colors for terminal output
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'


def print_colored(text: str, color: str):
    """Print colored text."""
    print(f"{color}{text}{Colors.RESET}")


def run_command(cmd: list, verbose: bool = False) -> int:
    """Run a shell command and return exit code."""
    if verbose:
        print_colored(f"Running: {' '.join(cmd)}", Colors.BLUE)
    
    result = subprocess.run(
        cmd,
        capture_output=not verbose,
        text=True,
    )
    
    if not verbose and result.stdout:
        print(result.stdout)
    
    if result.returncode != 0 and not verbose:
        print_colored(result.stderr, Colors.RED)
    
    return result.returncode


def run_tests(
    test_type: str = "all",
    coverage: bool = False,
    verbose: bool = False,
    fail_fast: bool = False,
    match_pattern: str = None,
    html: bool = False,
    xml: bool = False,
) -> int:
    """Run pytest with specified options."""
    
    # Base command
    cmd = ["python", "-m", "pytest"]
    
    # Add verbosity
    if verbose:
        cmd.append("-v")
    else:
        cmd.append("-v")  # Always verbose for better output
    
    # Add fail fast
    if fail_fast:
        cmd.append("-x")
    
    # Add coverage
    if coverage:
        cmd.extend(["--cov=app", "--cov-report=term-missing"])
        if html:
            cmd.append("--cov-report=html:tests/coverage_html")
        if xml:
            cmd.append("--cov-report=xml:tests/coverage.xml")
    
    # Add test selection
    if test_type == "unit":
        cmd.append("tests/unit")
    elif test_type == "integration":
        cmd.append("tests/integration")
    elif test_type == "e2e":
        cmd.append("tests/e2e")
    else:
        cmd.append("tests")
    
    # Add pattern matching
    if match_pattern:
        cmd.extend(["-k", match_pattern])
    
    # Add markers
    if test_type == "unit":
        cmd.extend(["-m", "unit"])
    elif test_type == "integration":
        cmd.extend(["-m", "integration"])
    elif test_type == "e2e":
        cmd.extend(["-m", "e2e"])
    
    # Add async support
    cmd.extend(["--asyncio-mode=auto"])
    
    # Print test run info
    print_colored(f"\n{'='*60}", Colors.BLUE)
    print_colored(f"Running {test_type.upper()} Tests", Colors.BLUE)
    print_colored(f"{'='*60}\n", Colors.BLUE)
    
    # Run tests
    exit_code = run_command(cmd, verbose=verbose)
    
    return exit_code


def check_test_environment() -> bool:
    """Check if test environment is properly configured."""
    print_colored("Checking test environment...", Colors.YELLOW)
    
    checks = {
        "Python version": sys.version_info >= (3, 9),
        "pytest installed": False,
        "pytest-asyncio installed": False,
        "pytest-cov installed": False,
        "Test directory exists": Path("tests").exists(),
        "app module exists": Path("app").exists(),
    }
    
    # Check pytest
    try:
        import pytest
        checks["pytest installed"] = True
    except ImportError:
        pass
    
    try:
        import pytest_asyncio
        checks["pytest-asyncio installed"] = True
    except ImportError:
        pass
    
    try:
        import pytest_cov
        checks["pytest-cov installed"] = True
    except ImportError:
        pass
    
    all_passed = all(checks.values())
    
    for check, passed in checks.items():
        status = f"{Colors.GREEN}✓{Colors.RESET}" if passed else f"{Colors.RED}✗{Colors.RESET}"
        print(f"  {status} {check}")
    
    if not all_passed:
        print_colored("\nMissing dependencies. Install with:", Colors.RED)
        print("  pip install pytest pytest-asyncio pytest-cov")
        return False
    
    print_colored("\nEnvironment OK!\n", Colors.GREEN)
    return True


def show_summary():
    """Show test summary."""
    print_colored(f"\n{'='*60}", Colors.BLUE)
    print_colored("Test Summary", Colors.BLUE)
    print_colored(f"{'='*60}\n", Colors.BLUE)
    
    # Count test files
    unit_tests = len(list(Path("tests/unit").glob("test_*.py"))) if Path("tests/unit").exists() else 0
    integration_tests = len(list(Path("tests/integration").glob("test_*.py"))) if Path("tests/integration").exists() else 0
    e2e_tests = len(list(Path("tests/e2e").glob("test_*.py"))) if Path("tests/e2e").exists() else 0
    
    print(f"  Unit test files: {unit_tests}")
    print(f"  Integration test files: {integration_tests}")
    print(f"  E2E test files: {e2e_tests}")
    
    print_colored("\nTest Categories:", Colors.YELLOW)
    print("  • unit - Fast, isolated tests for services")
    print("  • integration - API endpoint tests with database")
    print("  • e2e - End-to-end workflow tests")
    
    print_colored("\nExamples:", Colors.YELLOW)
    print("  python test_runner.py --unit")
    print("  python test_runner.py --integration --coverage")
    print("  python test_runner.py --all --match test_auth")
    print("  python test_runner.py --integration --fail-fast")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Test Runner for ProReadyEngineer Backend",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --unit                    Run unit tests
  %(prog)s --integration             Run integration tests
  %(prog)s --all --coverage          Run all tests with coverage
  %(prog)s --match test_auth         Run tests matching pattern
  %(prog)s --integration --fail-fast Stop on first failure
        """
    )
    
    # Test type selection
    parser.add_argument("--unit", action="store_true", help="Run only unit tests")
    parser.add_argument("--integration", action="store_true", help="Run only integration tests")
    parser.add_argument("--e2e", action="store_true", help="Run only E2E tests")
    parser.add_argument("--all", action="store_true", help="Run all tests (default)")
    
    # Coverage options
    parser.add_argument("--coverage", action="store_true", help="Generate coverage report")
    parser.add_argument("--html", action="store_true", help="Generate HTML coverage report")
    parser.add_argument("--xml", action="store_true", help="Generate XML coverage report")
    
    # Run options
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--fail-fast", "-x", action="store_true", help="Stop on first failure")
    parser.add_argument("--match", "-k", dest="pattern", help="Run tests matching pattern")
    parser.add_argument("--ci", action="store_true", help="CI/CD mode (strict exit codes)")
    
    # Other options
    parser.add_argument("--check", action="store_true", help="Check test environment only")
    parser.add_argument("--summary", action="store_true", help="Show test summary")
    
    args = parser.parse_args()
    
    # Show summary
    if args.summary:
        show_summary()
        return 0
    
    # Check environment
    if not check_test_environment():
        return 1
    
    if args.check:
        return 0
    
    # Determine test type
    test_type = "all"
    if args.unit:
        test_type = "unit"
    elif args.integration:
        test_type = "integration"
    elif args.e2e:
        test_type = "e2e"
    
    # Run tests
    exit_code = run_tests(
        test_type=test_type,
        coverage=args.coverage,
        verbose=args.verbose,
        fail_fast=args.fail_fast,
        match_pattern=args.pattern,
        html=args.html,
        xml=args.xml,
    )
    
    # Print result
    print()
    if exit_code == 0:
        print_colored("✓ All tests passed!", Colors.GREEN)
    else:
        print_colored(f"✗ Tests failed with exit code {exit_code}", Colors.RED)
    
    # Coverage report location
    if args.coverage and args.html:
        print_colored(f"\nHTML coverage report: tests/coverage_html/index.html", Colors.BLUE)
    
    if args.coverage and args.xml:
        print_colored(f"XML coverage report: tests/coverage.xml", Colors.BLUE)
    
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
