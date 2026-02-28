#!/usr/bin/env python3
"""
constants.py - Shared constants for fando-plan scripts

Centralizes magic numbers and configuration values used across multiple
modules to improve maintainability and prevent inconsistencies.

Usage:
    from constants import DEFAULT_CODEX_TIMEOUT, DEFAULT_SECURITY_LEVEL
"""


# ===========================================================================
# Codex CLI Configuration
# ===========================================================================

# Default timeout for Codex CLI execution (10 minutes)
DEFAULT_CODEX_TIMEOUT = 600

# Default timeout for short-lived Codex operations (2 minutes)
DEFAULT_CODEX_TIMEOUT_SHORT = 120


# ===========================================================================
# Review Configuration
# ===========================================================================

# Default security level for plan review when not specified
DEFAULT_SECURITY_LEVEL = "public"

# Valid security level names for CLI choices
# Note: This is just the list of valid level names for argparse/detection
# For full keyword-based detection metadata, see detect_security_level.py
SECURITY_LEVEL_CHOICES = ("personal", "internal", "public", "enterprise")


# ===========================================================================
# Training Data Constants
# ===========================================================================

# Minimum word length to consider a word "significant" for matching
SIGNIFICANT_WORD_MIN_LENGTH = 4

# Threshold for considering a finding "acted on" based on word overlap
FINDING_ADDRESS_THRESHOLD = 0.3

# Domain focus weights for training metrics
DOMAIN_FOCUS_WEIGHT_IN_LANE = 1.0
DOMAIN_FOCUS_WEIGHT_OUT_OF_LANE = 0.3
