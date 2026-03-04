"""Shared test fixtures for CLIReplay."""

import pathlib

import pytest


FIXTURE_DIR = pathlib.Path(__file__).parent / "fixtures"


@pytest.fixture
def fixture_dir():
    return FIXTURE_DIR


@pytest.fixture
def sample_header():
    return {
        "version": 1,
        "timestamp": "2026-03-04T12:00:00Z",
        "width": 80,
        "height": 24,
    }


@pytest.fixture
def sample_events():
    return [
        {"t": 0.0, "type": "o", "data": "$ "},
        {"t": 0.5, "type": "i", "data": "echo hello\r\n"},
        {"t": 0.6, "type": "o", "data": "echo hello\r\n"},
        {"t": 0.7, "type": "o", "data": "hello\r\n"},
        {"t": 1.0, "type": "o", "data": "$ "},
    ]
