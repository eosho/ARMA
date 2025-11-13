"""Validation-related type definitions for deployment state.

This module defines TypedDicts for validation results including parameter
validation, resource validation, and policy checks.

Set by: ValidationMiddleware, validation tools
Used by: Agent for validation feedback, pre-deployment checks
"""

from typing import TypedDict


class ValidationResultsDict(TypedDict, total=False):
    """Overall validation results.

    Set by: Validation middleware/tools
    Used by: Agent decision-making, user feedback
    """

    is_valid: bool
    """Whether all validations passed."""

    errors: list[str]
    """List of validation errors that must be fixed."""

    warnings: list[str]
    """List of validation warnings (non-blocking)."""

    checked_at: str
    """ISO 8601 timestamp when validation was performed."""


class ResourceValidationDict(TypedDict, total=False):
    """Resource naming and convention validation.

    Set by: Validation tools
    Used by: Pre-deployment validation
    """

    resource_name: str
    """Name of resource being validated."""

    resource_type: str
    """Azure resource type (e.g., 'Microsoft.Storage/storageAccounts')."""

    name_valid: bool
    """Whether resource name meets Azure naming requirements."""

    name_errors: list[str]
    """List of naming convention errors."""

    name_length_valid: bool
    """Whether name length is within allowed range."""

    min_length: int
    """Minimum allowed name length for this resource type."""

    max_length: int
    """Maximum allowed name length for this resource type."""

    character_validation: bool
    """Whether name contains only allowed characters."""

    allowed_characters: str
    """Description of allowed characters (e.g., 'alphanumeric and hyphens')."""

    globally_unique_required: bool
    """Whether resource name must be globally unique across Azure."""

    availability_checked: bool
    """Whether name availability was checked (for globally unique resources)."""

    name_available: bool
    """Whether name is available (only if availability_checked=True)."""
