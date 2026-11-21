"""Exceptions raised by the data layer."""

from __future__ import annotations


class GeodataError(Exception):
    """Base class for all errors of this package."""


class InvalidParcelId(GeodataError):
    """The text is not a cadastral parcel identifier (TERYT_type.precinct.number)."""


class ParcelNotFound(GeodataError):
    """ULDK has no parcel with this identifier or at this location."""


class UpstreamError(GeodataError):
    """A public service answered with an error or an unusable payload."""


class CacheMiss(GeodataError):
    """Offline mode is on and the requested entry is not in the cache."""
